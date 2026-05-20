$ErrorActionPreference = 'Stop'

$base = 'http://localhost:8000/api/v1'
$ts = [DateTimeOffset]::UtcNow.ToUnixTimeSeconds()
$adminEmail = "admin_full_$ts@org.invalid"
$employeeEmail = "employee_full_$ts@org.invalid"
$adminPass = 'Secret123!'
$employeePass = 'Secret123!'
$org = "org_full_$ts"

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

Write-Output "STEP=create_connection_valid"
$connName = "system_db_conn_full_$ts"
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

Write-Output "STEP=create_connection_invalid_expect_400"
$badConnStatus = 0
try {
  Invoke-WebRequest -Uri ($base + '/admin/connections') -Method Post -Headers @{ Authorization = "Bearer $adminToken" } -ContentType 'application/json' -Body (@{
    name = "bad_conn_$ts"
    db_type = 'mysql'
    method = 'form'
    host = 'mysql'
    port = 3306
    username = 'root'
    password = 'wrong-password'
    database_name = 'system_db'
  } | ConvertTo-Json) | Out-Null
} catch {
  if ($_.Exception.Response) {
    $badConnStatus = [int]$_.Exception.Response.StatusCode
  }
}

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
$csvResp = Invoke-WebRequest -UseBasicParsing -Uri ($base + '/export') -Method Post -Headers @{ Authorization = "Bearer $employeeToken" } -ContentType 'application/json' -Body (@{
  question = 'show database connections'
  format = 'csv'
} | ConvertTo-Json)

Write-Output "STEP=export_excel"
$xlsxResp = Invoke-WebRequest -UseBasicParsing -Uri ($base + '/export') -Method Post -Headers @{ Authorization = "Bearer $employeeToken" } -ContentType 'application/json' -Body (@{
  question = 'show database connections'
  format = 'excel'
} | ConvertTo-Json)

Write-Output "STEP=export_pdf"
$pdfResp = Invoke-WebRequest -UseBasicParsing -Uri ($base + '/export') -Method Post -Headers @{ Authorization = "Bearer $employeeToken" } -ContentType 'application/json' -Body (@{
  question = 'show database connections'
  format = 'pdf'
} | ConvertTo-Json)

Write-Output "RESULT_ADMIN=$adminEmail"
Write-Output "RESULT_EMPLOYEE=$employeeEmail"
Write-Output "RESULT_CONNECTION_ID=$connId"
Write-Output "RESULT_BAD_CONNECTION_STATUS=$badConnStatus"
Write-Output "RESULT_QUERY_ROWS=$($queryResp.rows.Count)"
Write-Output "RESULT_QUERY_COLUMNS=$($queryResp.columns -join ',')"
Write-Output "RESULT_CSV_STATUS=$($csvResp.StatusCode)"
Write-Output "RESULT_CSV_TYPE=$($csvResp.Headers['Content-Type'])"
Write-Output "RESULT_XLSX_STATUS=$($xlsxResp.StatusCode)"
Write-Output "RESULT_XLSX_TYPE=$($xlsxResp.Headers['Content-Type'])"
Write-Output "RESULT_PDF_STATUS=$($pdfResp.StatusCode)"
Write-Output "RESULT_PDF_TYPE=$($pdfResp.Headers['Content-Type'])"
