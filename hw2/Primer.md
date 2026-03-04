# Пример

## Создайте заказ и покажите, что товар зарезервировался

**Для начала надо получить токены, всегда обязательно, они истекают по времени!!! 5 минут и он сбрасывает по заданию**

```powershell
$userLogin = Invoke-RestMethod -Uri "http://localhost:8000/api/v1/auth/login" -Method Post -Headers @{"Content-Type"="application/json"} -Body (@{
    username="user"
    password="password123"
} | ConvertTo-Json)
$USER_TOKEN = $userLogin.access_token
Write-Host "Новый токен: $USER_TOKEN"
```

Результаты
```
PS C:\Users\Chikapushka\Desktop\marketplace> $userLogin = Invoke-RestMethod -Uri "http://localhost:8000/api/v1/auth/login" -Method Post 
-Headers @{"Content-Type"="application/json"} -Body (@{
>>     username="user"
>>     password="password123"
>> } | ConvertTo-Json)
PS C:\Users\Chikapushka\Desktop\marketplace> $USER_TOKEN = $userLogin.access_token
PS C:\Users\Chikapushka\Desktop\marketplace> Write-Host "Новый токен: $USER_TOKEN"
Новый токен: eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIzZTIzZDhlNi1lZDk5LTQ0NjMtOGYzNS00Yjg1NWVhZTlmYjEiLCJyb2xlIjoiVVNFUiIsImV4cC
I6MTc3MjAzNDA5NSwidHlwZSI6ImFjY2VzcyJ9.8mkZUxn4TX-Vh-RtuFDeH9MACaIDSJOt4OCPF47A8-A
```

**Показать текущий остаток товара**

```powershell
$product = Invoke-RestMethod -Uri "http://localhost:8000/api/v1/products/$PRODUCT_ID" -Method Get -Headers @{
    "Authorization" = "Bearer $USER_TOKEN"
}
Write-Host "Остаток до заказа: $($product.stock)"
```

Результаты
```
PS C:\Users\Chikapushka\Desktop\marketplace> $product = Invoke-RestMethod -Uri "http://localhost:8000/api/v1/products/$PRODUCT_ID" -Meth
od Get -Headers @{
>>     "Authorization" = "Bearer $USER_TOKEN"
>> }
PS C:\Users\Chikapushka\Desktop\marketplace> Write-Host "Остаток до заказа: $($product.stock)"
Остаток до заказа: 10
```

**Создать заказ**
```powershell
$order = Invoke-RestMethod -Uri "http://localhost:8000/api/v1/orders" -Method Post -Headers @{
    "Authorization" = "Bearer $USER_TOKEN"
    "Content-Type" = "application/json"
} -Body (@{
    items = @(@{ product_id = "$PRODUCT_ID"; quantity = 2 })
} | ConvertTo-Json -Depth 3)
```

Результаты
```
PS C:\Users\Chikapushka\Desktop\marketplace> $order = Invoke-RestMethod -Uri "http://localhost:8000/api/v1/orders" -Method Post -Headers
 @{
>>     "Authorization" = "Bearer $USER_TOKEN"
>>     "Content-Type" = "application/json"
>> } -Body (@{
>>     items = @(@{ product_id = "$PRODUCT_ID"; quantity = 2 })
>> } | ConvertTo-Json -Depth 3)
```

** Показать остаток после заказа**

```powershell
$product = Invoke-RestMethod -Uri "http://localhost:8000/api/v1/products/$PRODUCT_ID" -Method Get -Headers @{
    "Authorization" = "Bearer $USER_TOKEN"
}
Write-Host "Остаток после заказа: $($product.stock)"
```

Результаты
```
PS C:\Users\Chikapushka\Desktop\marketplace> $product = Invoke-RestMethod -Uri "http://localhost:8000/api/v1/products/$PRODUCT_ID" -Meth
od Get -Headers @{
>>     "Authorization" = "Bearer $USER_TOKEN"
>> }
PS C:\Users\Chikapushka\Desktop\marketplace> Write-Host "Остаток после заказа: $($product.stock)"
Остаток после заказа: 8
```

**Показать содержимое таблиц в БД**
```powershell
docker-compose exec db psql -U postgres -d marketplace -c "SELECT * FROM products WHERE id = '$PRODUCT_ID';"
```

Результаты
```
таблицы будут с бд
```

**Если заказать больше чем есть**
```powershell
PS C:\Users\Chikapushka\Desktop\marketplace> try {
>>     Invoke-RestMethod -Uri "http://localhost:8000/api/v1/orders" -Method Post -Headers @{
>>         "Authorization" = "Bearer $USER_TOKEN"
>>         "Content-Type" = "application/json"
>>     } -Body (@{
>>         items = @(@{ product_id = "$PRODUCT_ID"; quantity = 9999 })
>>     } | ConvertTo-Json -Depth 3)
>> } catch {
>>     $_.ErrorDetails.Message
>> }

{"detail":[{"type":"less_than_equal","loc":["body","items",0,"quantity"],"msg":"Input should be less than or equal to 999","input":9999,"ctx":{"le":999},"url":"https://errors.pydantic.dev/2.1
2/v/less_than_equal"}]}
```
quantity не может быть больше 999 (по заданию), вернулась ошибка 422 с детальным описанием

```powershell
PS C:\Users\Chikapushka\Desktop\marketplace> try {
>>     $order = Invoke-RestMethod -Uri "http://localhost:8000/api/v1/orders" -Method Post -Headers @{
>>         "Authorization" = "Bearer $USER_TOKEN"
>>         "Content-Type" = "application/json"
>>     } -Body (@{
>>         items = @(@{ product_id = "$PRODUCT_ID"; quantity = 500 })
>>     } | ConvertTo-Json -Depth 3)
>>     Write-Host "Заказ создан: $($order.id)"
>> } catch {
>>     Write-Host "Статус: $($_.Exception.Response.StatusCode.value__)"
>>     $_.ErrorDetails.Message
>> }
Статус: 409
{"error_code":"INSUFFICIENT_STOCK","message":"Insufficient stock for some products","details":{"products":[{"product_id":"76272f95-06dd-4298-9a5c-b894d0f126ab","requested":500,"available":10}
]}}
```
409 Conflict - статус, INSUFFICIENT_STOCK - код ошибки нехватки товара, details с информацией о том, сколько запросили и сколько есть в наличии

сразу заказ содавать низя ибо 5 минут ограничение опять же по заданию

удалить все заказы так моно(точнее отменить)

```
#Найти активный заказ
$activeOrders = docker-compose exec db psql -U postgres -d marketplace -t -c "SELECT id FROM orders WHERE user_id = (SELECT id FROM users WHERE username = 'user') AND status = 'CREATED';"

# Отменить каждый активный заказ
$activeOrders -split "`n" | ForEach-Object {
    $id = $_.Trim()
    if ($id) {
        Write-Host "Отменяем заказ: $id"
        $canceled = Invoke-RestMethod -Uri "http://localhost:8000/api/v1/orders/$id/cancel" -Method Post -Headers @{
            "Authorization" = "Bearer $USER_TOKEN"
        }
        Write-Host "Статус после отмены: $($canceled.status)"
    }
}

```

