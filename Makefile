CXX ?= c++
CXXFLAGS ?= -std=c++20 -O2 -Wall -Wextra -Wpedantic -Werror
ifneq ($(QF_SYSROOT),)
CXXFLAGS += -isysroot $(QF_SYSROOT)
endif

.PHONY: build test demo qualify clean
build: build/quantfabric
build/quantfabric: core/main.cpp qualification/build.py
	mkdir -p build
	python3 -m qualification.build --compiler "$(CXX)" --flags "$(CXXFLAGS)"
test: build
	python3 -m unittest discover -s tests -v
demo: build
	python3 -m qualification.run --events 5000 --controls --output evidence/runs/demo
qualify: build
	python3 -m qualification.run --events 250000 --seeds 7 19 41 73 --controls --output evidence/runs/million
clean:
	rm -rf build
