package main

//go:generate go run github.com/cilium/ebpf/cmd/bpf2go -cc clang -target bpf -cflags "-g -O2 -Wall" process bpf/process.bpf.c
//go:generate go run github.com/cilium/ebpf/cmd/bpf2go -cc clang -target bpf -cflags "-g -O2 -Wall" oom bpf/oom.bpf.c
//go:generate go run github.com/cilium/ebpf/cmd/bpf2go -cc clang -target bpf -cflags "-g -O2 -Wall" tcp bpf/tcp.bpf.c
