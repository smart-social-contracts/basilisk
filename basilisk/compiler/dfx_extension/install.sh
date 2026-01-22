#!/bin/bash

DFX_CACHE_DIR="$(dfx cache show)"

if [ ! -d "$DFX_CACHE_DIR" ]; then
    dfx cache install
fi

mkdir -p "$DFX_CACHE_DIR/extensions/basilisk"
cp extension.json "$DFX_CACHE_DIR/extensions/basilisk/extension.json"
