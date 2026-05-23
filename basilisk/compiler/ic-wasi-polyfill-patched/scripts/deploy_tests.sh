#!/bin/bash

cd tests/canister_initial

icp canister create canister_initial_backend

pwd

ls

icp canister install --mode reinstall -y --wasm target/wasm32-wasip1/release/canister_initial_backend_nowasi.wasm canister_initial_backend 


