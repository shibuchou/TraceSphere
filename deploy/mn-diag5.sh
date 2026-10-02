#!/usr/bin/env bash
set -u
SP=/var/lib/zstack/virtualenv/zstackctl/lib/python2.7/site-packages
echo "== zstackctl package =="
ls "$SP" | grep -i zstack
echo
echo "== reset_password impl =="
grep -rn reset_password "$SP/zstackctl" 2>/dev/null | head
echo
echo "== show relevant file =="
F=$(grep -rln reset_password "$SP/zstackctl" 2>/dev/null | head -1)
echo "file=$F"
if [ -n "${F:-}" ]; then grep -n -A 25 reset_password "$F" | head -60; fi
