# Makefile for ambient-expense-agent

install:
	@echo "Installing dependencies..."
	agents-cli install

playground:
	@echo "Launching agent playground..."
	agents-cli playground --port 8080

generate-traces:
	@echo "Generating evaluation traces..."
	.venv/bin/python tests/eval/generate_traces.py

grade:
	@echo "Grading evaluation traces..."
	agents-cli eval grade --traces artifacts/traces/generated_traces.json --config tests/eval/eval_config.yaml
