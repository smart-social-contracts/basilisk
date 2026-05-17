import Prim "mo:⛔";
import Nat64 "mo:base/Nat64";
import Text "mo:base/Text";
import Iter "mo:base/Iter";
import Array "mo:base/Array";
import Nat "mo:base/Nat";
import Order "mo:base/Order";
import HashMap "mo:base/HashMap";

actor Counter {

    transient var count : Nat64 = 0;

    type BenchmarkResult = {
        body_instructions : Nat64;
        total_instructions : Nat64;
        result : Nat64;
    };

    type BenchmarkResultText = {
        body_instructions : Nat64;
        total_instructions : Nat64;
        result : Text;
    };

    public query func bench_noop() : async BenchmarkResult {
        let start = Prim.performanceCounter(0);
        let end = Prim.performanceCounter(0);
        {
            body_instructions = end - start;
            total_instructions = Prim.performanceCounter(1);
            result = 0;
        };
    };

    public func bench_increment() : async BenchmarkResult {
        let start = Prim.performanceCounter(0);
        count += 1;
        let end = Prim.performanceCounter(0);
        {
            body_instructions = end - start;
            total_instructions = Prim.performanceCounter(1);
            result = count;
        };
    };

    public query func bench_fibonacci() : async BenchmarkResult {
        let start = Prim.performanceCounter(0);
        var a : Nat64 = 0;
        var b : Nat64 = 1;
        var i : Nat = 0;
        while (i < 25) {
            let tmp = b;
            b := a + b;
            a := tmp;
            i += 1;
        };
        let end = Prim.performanceCounter(0);
        {
            body_instructions = end - start;
            total_instructions = Prim.performanceCounter(1);
            result = a;
        };
    };

    func fibRecursive(n : Nat) : Nat {
        if (n <= 1) { return n };
        fibRecursive(n - 1) + fibRecursive(n - 2);
    };

    public query func bench_fibonacci_recursive() : async BenchmarkResult {
        let start = Prim.performanceCounter(0);
        let result = fibRecursive(20);
        let end = Prim.performanceCounter(0);
        {
            body_instructions = end - start;
            total_instructions = Prim.performanceCounter(1);
            result = Nat64.fromNat(result);
        };
    };

    public query func bench_string_ops() : async BenchmarkResultText {
        let start = Prim.performanceCounter(0);
        var s = "";
        var i : Nat = 0;
        while (i < 100) {
            s := s # Nat.toText(i);
            i += 1;
        };
        let chars = Text.toArray(s);
        let len = if (chars.size() > 50) { 50 } else { chars.size() };
        let slice = Array.tabulate<Char>(len, func(j) { chars[j] });
        let result = Text.fromIter(Iter.fromArray(slice));
        let end = Prim.performanceCounter(0);
        {
            body_instructions = end - start;
            total_instructions = Prim.performanceCounter(1);
            result = result;
        };
    };

    public query func bench_list_ops() : async BenchmarkResult {
        let start = Prim.performanceCounter(0);
        let arr = Array.tabulate<Nat64>(500, func(i) : Nat64 {
            Nat64.fromNat(500 - i);
        });
        let sorted = Array.sort<Nat64>(arr, func(a : Nat64, b : Nat64) : Order.Order {
            Nat64.compare(a, b);
        });
        let end = Prim.performanceCounter(0);
        {
            body_instructions = end - start;
            total_instructions = Prim.performanceCounter(1);
            result = sorted[0];
        };
    };

    public query func bench_dict_ops() : async BenchmarkResult {
        let start = Prim.performanceCounter(0);
        let map = HashMap.HashMap<Text, Nat64>(16, Text.equal, Text.hash);
        var i : Nat64 = 0;
        while (i < 500) {
            map.put(Nat64.toText(i), i * i);
            i += 1;
        };
        var total : Nat64 = 0;
        i := 0;
        while (i < 500) {
            switch (map.get(Nat64.toText(i))) {
                case (?v) { total += v };
                case null {};
            };
            i += 1;
        };
        let end = Prim.performanceCounter(0);
        {
            body_instructions = end - start;
            total_instructions = Prim.performanceCounter(1);
            result = total;
        };
    };

    public query func bench_method_overhead() : async BenchmarkResult {
        {
            body_instructions = 0;
            total_instructions = Prim.performanceCounter(1);
            result = 0;
        };
    };
};
