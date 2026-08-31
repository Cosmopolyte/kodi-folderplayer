#!/bin/bash
# usage: rpc.sh METHOD 'PARAMS-JSON'
curl -s -m10 http://127.0.0.1:8090/jsonrpc -H 'Content-Type: application/json' -d "{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"$1\",\"params\":${2:-{\}}}"; echo
