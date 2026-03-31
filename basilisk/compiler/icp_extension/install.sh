#!/bin/bash

ICP_CACHE_DIR="$(icp cache show)"

if [ ! -d "$ICP_CACHE_DIR" ]; then
    icp cache install
fi

mkdir -p "$ICP_CACHE_DIR/extensions/basilisk"
cp extension.json "$ICP_CACHE_DIR/extensions/basilisk/extension.json"
