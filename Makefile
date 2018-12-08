update:
	pipenv update

test:
	pipenv run py.test -v --benchmark-skip

benchmark:
	pipenv run py.test -v --benchmark-only \
		--benchmark-min-rounds=5 \
		--benchmark-sort=min \
		--benchmark-json=benchmark_results.json

docs:
	pipenv run sphinx-apidoc --force --separate -o docs/api gymwipe gymwipe/test gymwipe/*/test
	$(MAKE) -C docs clean
	$(MAKE) -C docs html
	# Open docs/_build/html/index.html to see the results

requirements:
	pipenv run pipenv_to_requirements
	cat requirements.txt | grep -v "#" >> requirements-dev.txt

ode:
	pipenv run pip install py3ode pygame

.PHONY: update test benchmark docs requirements ode