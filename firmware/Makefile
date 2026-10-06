.PHONY: test build flash
test:
	g++ -std=c++17 -Wall -Wextra -Werror -Ilib/core test/test_core.cpp -o .test_core && ./.test_core
build:
	pio run -e esp32dev
flash:
	pio run -e esp32dev -t upload && pio device monitor
