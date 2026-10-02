VMLINUX := bpf/vmlinux.h
GO      ?= go
BPFTOOL ?= bpftool
CLANG   ?= clang

.PHONY: all vmlinux generate build clean run

all: build

bpf/vmlinux.h:
	$(BPFTOOL) btf dump file /sys/kernel/btf/vmlinux format c > $@

vmlinux: $(VMLINUX)

generate: $(VMLINUX)
	$(GO) generate ./...

build: generate
	$(GO) build -o bin/vm-agent .

run: build
	sudo ./bin/vm-agent

clean:
	rm -rf bin *.o bpf/*.o bpf/vmlinux.h *_bpfel.go *_bpfeb.go
