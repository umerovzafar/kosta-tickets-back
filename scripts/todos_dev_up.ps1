# Запуск зависимостей для сервиса todos (БД + auth + сам todos) с пробросом :1240.
# Требуется Docker Desktop и файл .env в корне tickets-back (см. .env.example).
# Использование: из корня репозитория  .\scripts\todos_dev_up.ps1

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

Write-Host "Starting todos_db, users_db, auth, todos (with port 1240)..." -ForegroundColor Cyan
docker compose -f docker-compose.yml -f docker-compose.todos-dev.yml up -d users_db todos_db auth todos

if ($LASTEXITCODE -ne 0) {
    Write-Host "Docker compose failed. Убедитесь, что Docker Desktop запущен." -ForegroundColor Red
    exit $LASTEXITCODE
}

Write-Host ""
Write-Host "Когда контейнеры healthy, проверьте:" -ForegroundColor Green
Write-Host "  curl.exe -s http://127.0.0.1:1240/health"
Write-Host ""
Write-Host "Для API через gateway (как фронт):" -ForegroundColor Green
Write-Host "  docker compose up -d gateway"
Write-Host "  curl.exe -s http://127.0.0.1:1234/health/todos"
