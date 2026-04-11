#!/bin/bash

aicaller batch_request batch.jsonl -r api_results.jsonl -c api.yaml -a --cont --only_output > api_request.txt
