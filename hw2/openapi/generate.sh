#!/bin/bash

# Генерация кода из OpenAPI спецификации
docker run --rm -v ${PWD}:/local openapitools/openapi-generator-cli generate -i /local/openapi/openapi.yaml -g python-fastapi -o /local/generated --additional-properties=packageName=marketplace_api


echo "Генерация кода завершена"