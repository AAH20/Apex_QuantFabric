// SPDX-License-Identifier: Apache-2.0
#include <algorithm>
#include <array>
#include <charconv>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <cstdlib>
#include <iomanip>
#include <iostream>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>

struct Event {
    std::string kind;
    std::int64_t time, session, id, instrument, sequence, watermark;
    std::int64_t model, policy, config, expiry, quantity, action;
    double score;
};
struct Slot { std::int64_t id=0, instrument=0, quantity=0; bool uncertain=false; };
struct Result { std::string disposition; bool valid=false; std::int64_t action=0; bool has_score=false; double score=0; };

std::int64_t integer(const std::string& s) {
    std::int64_t n=0;
    auto [end, error]=std::from_chars(s.data(),s.data()+s.size(),n);
    if (error!=std::errc{} || end!=s.data()+s.size() || n<0 || n>2147483647)
        throw std::runtime_error("invalid integer");
    return n;
}
Event parse(const std::string& line) {
    std::vector<std::string> parts;
    std::istringstream input(line); std::string part;
    while (std::getline(input,part,'\t')) parts.push_back(part);
    if (parts.size()!=14) throw std::runtime_error("expected fourteen TSV columns");
    char* end=nullptr;
    const double score=std::strtod(parts[11].c_str(),&end);
    if (parts[11].empty() || end!=parts[11].c_str()+parts[11].size()) throw std::runtime_error("invalid score");
    Event e{parts[0],integer(parts[1]),integer(parts[2]),integer(parts[3]),integer(parts[4]),integer(parts[5]),integer(parts[6]),integer(parts[7]),integer(parts[8]),integer(parts[9]),integer(parts[10]),integer(parts[12]),integer(parts[13]),score};
    const std::array<std::string,7> kinds{"MARKET","PREDICTION","DROPPED","UNCERTAIN","RELEASE","RESET","ADVANCE"};
    if (std::find(kinds.begin(),kinds.end(),e.kind)==kinds.end() || e.session==0 || e.instrument>=8)
        throw std::runtime_error("unknown kind, invalid session or instrument");
    if ((e.kind=="PREDICTION" || e.kind=="DROPPED") && (e.id<1 || e.id>256 || e.quantity<1 || e.quantity>16))
        throw std::runtime_error("prediction bounds");
    if (e.kind=="MARKET" && (e.sequence==0 || !std::isfinite(score) || score<1 || score>2147483647 || std::floor(score)!=score))
        throw std::runtime_error("market bounds");
    if ((e.kind=="UNCERTAIN" || e.kind=="RELEASE") && (e.action<1 || e.action>256))
        throw std::runtime_error("action bounds");
    // Unused columns must be zero: one unambiguous, canonical frame per event.
    if (e.kind=="MARKET" && (e.id || e.watermark || e.model || e.policy || e.config || e.expiry || e.quantity || e.action)) throw std::runtime_error("unused market fields");
    if ((e.kind=="PREDICTION" || e.kind=="DROPPED") && (e.sequence || e.action)) throw std::runtime_error("unused prediction fields");
    if (e.kind=="UNCERTAIN" || e.kind=="RELEASE" || e.kind=="RESET" || e.kind=="ADVANCE") {
        if (e.id || e.instrument || e.sequence || e.watermark || e.model || e.policy || e.config || e.expiry || e.score!=0 || e.quantity)
            throw std::runtime_error("unused control fields");
        if ((e.kind=="RESET" || e.kind=="ADVANCE") && e.action) throw std::runtime_error("unused action");
    }
    return e;
}

class Kernel {
    std::int64_t session_=1;
    std::array<std::int64_t,8> watermarks_{}, prices_{};
    std::array<bool,8> blocked_{};
    std::array<std::uint64_t,4> seen_{};
    std::array<Slot,16> slots_{};
    std::string variant_;
    bool mutant(const std::string& name) const { return variant_==name; }
public:
    explicit Kernel(std::string variant): variant_(std::move(variant)) {}
    Result step(const Event& e) {
        Result r; auto done=[&](const char* code) { r.disposition=code; return r; };
        if (e.kind=="RESET") {
            if (e.session<=session_) return done("RESET_OLD");
            for (const auto& s:slots_) if (s.id) return done("RESET_BLOCKED");
            session_=e.session; watermarks_.fill(0); prices_.fill(0); blocked_.fill(false); seen_.fill(0);
            return done("RESET");
        }
        if (e.session!=session_ && !(mutant("wrong_session") && e.kind=="PREDICTION")) return done("WRONG_SESSION");
        if (e.kind=="ADVANCE") return done("ADVANCE");
        if (e.kind=="MARKET") {
            const auto i=static_cast<std::size_t>(e.instrument);
            if (blocked_[i]) return done("FEED_BLOCKED");
            if (e.sequence<=watermarks_[i]) return done("MARKET_DUPLICATE");
            if (e.sequence!=watermarks_[i]+1) { blocked_[i]=true; return done("FEED_GAP"); }
            watermarks_[i]=e.sequence; prices_[i]=static_cast<std::int64_t>(e.score);
            return done("MARKET");
        }
        if (e.kind=="UNCERTAIN" || e.kind=="RELEASE") {
            for (auto& s:slots_) if (s.id==e.action) {
                if (e.kind=="UNCERTAIN" && !mutant("release_uncertain")) { s.uncertain=true; return done("UNRESOLVED"); }
                s=Slot{}; return done("RELEASED");
            }
            return done("UNKNOWN_ACTION");
        }
        const auto word=static_cast<std::size_t>((e.id-1)/64);
        const auto bit=std::uint64_t{1} << ((e.id-1)%64);
        if ((seen_[word]&bit) && !mutant("double_commit")) return done("DUPLICATE");
        seen_[word]|=bit;
        if (e.kind=="DROPPED") return done("QUEUE_DROPPED");
        r.has_score=true; r.score=e.score+(mutant("equivalent")?1e-8:0);
        const auto i=static_cast<std::size_t>(e.instrument);
        if (e.model!=1 || e.policy!=1 || e.config!=1) return done("WRONG_VERSION");
        if (blocked_[i]) return done("FEED_BLOCKED");
        if ((watermarks_[i]==0 || e.watermark!=watermarks_[i]) && !mutant("stale_accept")) return done("STALE_WATERMARK");
        const auto arrival=e.time+(mutant("late_result")?5:0);
        if (arrival>e.expiry && !mutant("expiry_accept")) return done("EXPIRED");
        const double reference=static_cast<double>((prices_[i]%101)-50)/50.0;
        if ((!std::isfinite(r.score) || std::abs(r.score-reference)>1e-6) && !mutant("numerical_accept")) return done("NUMERICAL");
        r.valid=true;
        if (r.score<(mutant("threshold_shift")?0.6:0.5)) return done("NO_SIGNAL");
        std::int64_t used=0;
        for (const auto& s:slots_) if (s.id && s.instrument==e.instrument) used+=s.quantity;
        if (used+e.quantity>16 && !mutant("ignore_capacity")) return done("CAPACITY_UNITS");
        for (auto& s:slots_) if (!s.id) {
            s={e.id,e.instrument,e.quantity,false}; r.action=e.id; return done("ADMITTED");
        }
        return done("CAPACITY_SLOTS");
    }
    void emit(std::size_t index,const Result& r,std::int64_t ns) const {
        std::cout << index << '\t' << r.disposition << '\t' << r.valid << '\t' << r.action << '\t';
        if (r.has_score) {
            if (std::isfinite(r.score)) std::cout << std::setprecision(17) << r.score;
            else if (std::isnan(r.score)) std::cout << "nan";
            else std::cout << (r.score>0?"inf":"-inf");
        } else std::cout << '-';
        std::cout << '\t' << session_ << '\t';
        for (std::size_t i=0;i<8;++i) { if (i) std::cout << ','; std::cout << watermarks_[i]; }
        std::cout << '\t';
        for (std::size_t i=0;i<8;++i) { if (i) std::cout << ','; std::cout << prices_[i]; }
        unsigned mask=0; for (unsigned i=0;i<8;++i) if (blocked_[i]) mask|=1U<<i;
        std::cout << '\t' << mask << '\t' << std::hex << std::setfill('0');
        for (int i=3;i>=0;--i) std::cout << std::setw(16) << seen_[static_cast<std::size_t>(i)];
        std::cout << std::dec << std::setfill(' ') << '\t';
        auto copy=slots_; std::sort(copy.begin(),copy.end(),[](const Slot& a,const Slot& b){return a.id<b.id;});
        bool first=true;
        for (const auto& s:copy) if (s.id) {
            if (!first) std::cout << ';';
            first=false;
            std::cout << s.id << ':' << s.instrument << ':' << s.quantity << ':' << s.uncertain;
        }
        if (first) std::cout << '-';
        std::cout << '\t' << ns << '\n';
    }
};
int main(int argc,char** argv) {
    const std::string variant=argc==2?argv[1]:"baseline";
    const std::array<std::string,11> variants{"baseline","equivalent","stale_accept","expiry_accept","wrong_session","release_uncertain","ignore_capacity","double_commit","threshold_shift","numerical_accept","late_result"};
    if (argc>2 || std::find(variants.begin(),variants.end(),variant)==variants.end()) { std::cerr << "unknown variant\n"; return 2; }
    Kernel kernel(variant); std::string line; std::size_t index=0; std::int64_t time=-1;
    try {
        while (std::getline(std::cin,line)) {
            const auto e=parse(line);
            if (e.time<time) throw std::runtime_error("logical time regressed");
            time=e.time;
            const auto start=std::chrono::steady_clock::now();
            const auto result=kernel.step(e);
            const auto ns=std::chrono::duration_cast<std::chrono::nanoseconds>(std::chrono::steady_clock::now()-start).count();
            kernel.emit(index++,result,ns);
        }
        if (!std::cin.eof() || !std::cout.good()) throw std::runtime_error("I/O failed");
    } catch (const std::exception& e) { std::cerr << "input " << index << ": " << e.what() << '\n'; return 2; }
}
