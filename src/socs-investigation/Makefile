CC       = gcc
CFLAGS   = -pthread -Wall -O2 -D_GNU_SOURCE
LDFLAGS  = -lgpiod -lrt

COMMON_SRC = main.c utils.c log_writer.c gpio_handler.c
COMMON_OBJ = $(COMMON_SRC:.c=.o)

BOARD    ?= bvc
TARGET   = $(BOARD)-monitor
CFLAGS  += -DBOARD_$(BOARD)

OBJS     = $(COMMON_OBJ)

VALID_BOARDS = bvc bcvm starfive lichee radxa bvc_arm mangopi rockpi4 repkapi4

.PHONY: all clean check-board

all: check-board $(TARGET)

check-board:
	@valid=0; \
	for b in $(VALID_BOARDS); do \
		if [ "$$b" = "$(BOARD)" ]; then valid=1; break; fi; \
	done; \
	if [ "$$valid" -eq 0 ]; then \
		echo "Error: Unknown BOARD='$(BOARD)'"; \
		echo "Valid boards: $(VALID_BOARDS)"; \
		echo "Usage: make BOARD=<board>"; \
		exit 1; \
	fi

$(TARGET): $(OBJS)
	$(CC) $(CFLAGS) -o $@ $^ $(LDFLAGS)
	@echo "Built $(TARGET) for board $(BOARD)"

%.o: %.c
	$(CC) $(CFLAGS) -c -o $@ $<

clean:
	rm -f *.o *-monitor
