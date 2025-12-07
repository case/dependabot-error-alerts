.PHONY: deps test typecheck build

deps:
	npm install

test: typecheck
	npm test

typecheck:
	npm run typecheck

build:
	npm run build
