# Read only local counters. Each group can fail without hiding the other groups.
# A missing value is left out of the result; it is never replaced with zero.
$ErrorActionPreference = 'Stop'
$r = @{}

# Average CPU use across chips, weighted by how many logical processors each has.
try {
    $chips = @(Get-CimInstance Win32_Processor -Property LoadPercentage,NumberOfLogicalProcessors -OperationTimeoutSec 3)
    $busy = 0.0; $cores = 0
    foreach ($chip in $chips) {
        if ($null -eq $chip.LoadPercentage -or $chip.LoadPercentage -gt 100 -or $chip.NumberOfLogicalProcessors -lt 1) { throw 'CPU unavailable' }
        $busy += $chip.LoadPercentage * $chip.NumberOfLogicalProcessors
        $cores += $chip.NumberOfLogicalProcessors
    }
    if ($cores -gt 0) { $r.cpu_percent = $busy / $cores }
} catch { }

# Windows reports memory in KiB and boot time as a date. Convert for the report.
try {
    $os = Get-CimInstance Win32_OperatingSystem -Property TotalVisibleMemorySize,FreePhysicalMemory,LastBootUpTime -OperationTimeoutSec 3
    if ($null -ne $os.FreePhysicalMemory -and $os.TotalVisibleMemorySize -gt 0 -and $os.FreePhysicalMemory -le $os.TotalVisibleMemorySize) {
        $r.ram_percent = 100.0 * (1.0 - $os.FreePhysicalMemory / $os.TotalVisibleMemorySize)
        $r.ram_free_gib = $os.FreePhysicalMemory / 1048576.0
    }
    if ($null -ne $os.LastBootUpTime) { $r.uptime_hours = ((Get-Date) - $os.LastBootUpTime).TotalHours }
} catch { }

# Count active network interfaces without making a network connection.
try {
    $links = [System.Net.NetworkInformation.NetworkInterface]::GetAllNetworkInterfaces()
    $r.links_up = @($links | Where-Object { $_.OperationalStatus -eq 'Up' -and $_.NetworkInterfaceType -notin 'Loopback','Tunnel' }).Count
} catch { }

# Read the printing service state without sending a print job.
try { $r.spooler = (Get-Service -Name Spooler).Status.ToString() } catch { }
$r | ConvertTo-Json -Compress
