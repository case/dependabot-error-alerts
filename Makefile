.PHONY: deps test typecheck build check-dist

deps:
	npm install

test: typecheck check-dist
	npm test

typecheck:
	npm run typecheck

build:
	npm run build

check-dist: build
	@if [ -n "$$(git status --porcelain dist/)" ]; then \
		echo "Error: dist/ is out of date. Run 'make build' and commit the changes."; \
		git diff dist/; \
		exit 1; \
	fi
