import assert from "node:assert/strict";
import fs from "node:fs";
import vm from "node:vm";

const source = fs.readFileSync("frontend/js/main.js", "utf8");
const storage = new Map([["aura_access_token", "test-token"]]);
const context = {
    AbortController,
    Headers,
    clearTimeout,
    console,
    document: { addEventListener() {}, getElementById() { return null; } },
    fetch: async () => ({
        ok: true,
        status: 200,
        headers: { get: () => "text/plain" },
        text: async () => "not json",
    }),
    sessionStorage: {
        getItem: (key) => storage.get(key) ?? null,
        removeItem: (key) => storage.delete(key),
        setItem: (key, value) => storage.set(key, value),
    },
    AuraNotifications: { stop() {}, start() {} },
    setTimeout,
    showAuthPanel() {},
};
vm.createContext(context);
vm.runInContext(source, context);

await assert.rejects(
    context.apiJson("/non-json-success"),
    /Invalid JSON response/,
    "successful non-JSON responses must be contract failures",
);

context.fetch = async () => ({
    ok: true,
    status: 200,
    headers: { get: () => "application/json" },
    json: async () => { throw new Error("malformed"); },
});
await assert.rejects(context.apiJson("/malformed-json"), /Invalid JSON response/);

context.fetch = async () => ({
    ok: false,
    status: 401,
    headers: { get: () => "application/json" },
    json: async () => ({ detail: "unauthorized" }),
});
await assert.rejects(context.apiJson("/unauthorized"), /unauthorized/);
assert.equal(storage.has("aura_access_token"), false, "401 must clear authentication state");

console.log("frontend API contract checks passed");
