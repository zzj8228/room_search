$ErrorActionPreference = 'Stop'
$taskBrowser = 'agent-browser.cmd'
$taskSession = 'pku-classroom-location-regression'
& $taskBrowser --session $taskSession open 'http://127.0.0.1:8766/?date=2026-10-21'
if ($LASTEXITCODE -ne 0) { throw '无法打开教室查课页面。' }
& $taskBrowser --session $taskSession wait --fn "document.getElementById('result-count').textContent!=='—'"
if ($LASTEXITCODE -ne 0) { throw '页面未完成初始化。' }
& $taskBrowser --session $taskSession snapshot -i -d 1 | Out-Null
$taskScript = @'
(() => {
  const room = document.getElementById('room');
  const building = document.getElementById('building');
  room.value = '理教-307';
  building.value = '二教';
  building.dispatchEvent(new Event('change', {bubbles: true}));
  if (room.value !== '') throw new Error('切换二教后仍保留旧教室：' + room.value);
  if (room.tagName !== 'SELECT') throw new Error('教室控件不是可选的下拉列表');
  const values = Array.from(room.options).map(option => option.value).filter(Boolean);
  if (!values.length || values.some(value => !value.startsWith('二教-'))) {
    throw new Error('教室列表没有随教学楼筛选');
  }
  room.value = values[0];
  if (room.value !== values[0]) throw new Error('无法选择新教室');
  building.value = '';
  building.dispatchEvent(new Event('change', {bubbles: true}));
  if (room.value !== values[0]) throw new Error('切换到全部教学楼时丢失了仍有效的教室');
  return {passed: true, selected: room.value, buildingRooms: values.length};
})()
'@
$taskResult = ($taskScript | & $taskBrowser --session $taskSession eval --stdin --json) | ConvertFrom-Json
if (!$taskResult.success) { throw ($taskResult.error | Out-String) }
$taskResult.data.result | ConvertTo-Json
