$ErrorActionPreference = 'Stop'

$base = 'http://localhost:8000/api/v1'
$ts = [DateTimeOffset]::UtcNow.ToUnixTimeSeconds()
$adminEmail = "admin_$ts@org.invalid"
$employeeEmail = "employee_$ts@org.invalid"
$adminPass = 'Secret123!'
$employeePass = 'Secret123!'
$org = "org_$ts"

Write-Output "STEP=register_admin"
Invoke-RestMethod -Uri ($base + '/auth/register') -Method Post -ContentType 'application/json' -Body (@{
  organisation = $org
  email = $adminEmail
  full_name = 'Admin'
  password = $adminPass
  role = 'admin'
} | ConvertTo-Json) | Out-Null

Write-Output "STEP=login_admin"
$adminLogin = Invoke-RestMethod -Uri ($base + '/auth/login') -Method Post -ContentType 'application/json' -Body (@{
  organisation = $org
  email = $adminEmail
  password = $adminPass
} | ConvertTo-Json)
$adminToken = $adminLogin.access_token

Write-Output "STEP=create_employee"
$employeeCreated = Invoke-RestMethod -Uri ($base + '/admin/employees') -Method Post -Headers @{ Authorization = "Bearer $adminToken" } -ContentType 'application/json' -Body (@{
  organisation = $org
  email = $employeeEmail
  full_name = 'Employee'
  password = $employeePass
  role = 'employee'
} | ConvertTo-Json)
$employeeId = $employeeCreated.id

Write-Output "STEP=create_connection"
$connName = "system_db_conn_$ts"
$conn = Invoke-RestMethod -Uri ($base + '/admin/connections') -Method Post -Headers @{ Authorization = "Bearer $adminToken" } -ContentType 'application/json' -Body (@{
  name = $connName
  db_type = 'mysql'
  method = 'form'
  host = 'mysql'
  port = 3306
  username = 'root'
  password = 'root'
  database_name = 'system_db'
} | ConvertTo-Json)
$connId = $conn.id

Write-Output "STEP=assign_permissions"
Invoke-RestMethod -Uri ($base + '/admin/permissions') -Method Post -Headers @{ Authorization = "Bearer $adminToken" } -ContentType 'application/json' -Body (@{
  employee_id = $employeeId
  connection_ids = @($connId)
} | ConvertTo-Json) | Out-Null

Write-Output "STEP=login_employee"
$employeeLogin = Invoke-RestMethod -Uri ($base + '/auth/login') -Method Post -ContentType 'application/json' -Body (@{
  organisation = $org
  email = $employeeEmail
  password = $employeePass
} | ConvertTo-Json)
$employeeToken = $employeeLogin.access_token

Write-Output "STEP=query"
$queryResp = Invoke-RestMethod -Uri ($base + '/query') -Method Post -Headers @{ Authorization = "Bearer $employeeToken" } -ContentType 'application/json' -Body (@{
  question = 'show database connections'
} | ConvertTo-Json)

Write-Output "STEP=export_csv"
$exportResp = Invoke-WebRequest -UseBasicParsing -Uri ($base + '/export') -Method Post -Headers @{ Authorization = "Bearer $employeeToken" } -ContentType 'application/json' -Body (@{
  question = 'show database connections'
  format = 'csv'
} | ConvertTo-Json)

Write-Output "ADMIN=$adminEmail"
Write-Output "EMPLOYEE=$employeeEmail"
Write-Output "CONNECTION_ID=$connId"
Write-Output "QUERY_SQL=$($queryResp.generated_sql)"
Write-Output "QUERY_ROWS=$($queryResp.rows.Count)"
Write-Output "QUERY_COLUMNS=$($queryResp.columns -join ',')"
Write-Output "EXPORT_STATUS=$($exportResp.StatusCode)"
Write-Output "EXPORT_TYPE=$($exportResp.Headers['Content-Type'])"
