"use strict";
const $ = (id) => document.getElementById(id);
const state = {meta: null, page: 1, response: null, sequence: 0, locations: [], syncing: false};
const urlState = new URLSearchParams(location.search);
const number = (n) => new Intl.NumberFormat("zh-CN").format(n);
function element(tag, cls, content) {
  const node = document.createElement(tag); if (cls) node.className = cls;
  if (content !== undefined) node.textContent = content; return node;
}
async function api(path, options) {
  const response = await fetch(path, options);
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || "查询失败，请稍后重试。");
  return data;
}
function message(id, text) { $(id).textContent = text; $(id).hidden = !text; }
function periodLabel(periods) {
  if (periods.length === 1) return "第 " + periods[0] + " 节";
  return "第 " + periods[0] + "–" + periods.at(-1) + " 节";
}
function modeChanged() {
  for (const type of ["period", "time", "range"]) $(type + "-fields").hidden = $("mode").value !== type;
  document.querySelectorAll(".period-chip").forEach((button) => {
    const n = Number(button.dataset.number);
    const active = $("mode").value === "period" && n >= Number($("period-from").value) && n <= Number($("period-to").value);
    button.classList.toggle("active", active); button.setAttribute("aria-pressed", String(active));
  });
}
function updateTermNote() {
  const item = state.meta.calendar.semesters.find((x) => x.id === $("term").value);
  $("term-note").textContent = item ? item.label + " · " + item.start + " 至 " + item.end + "（含首尾日期）。学期仅按上课日期划分。" :
    "按校本部校历划分秋、春、夏三学期；暑期学校独立划分，寒暑假、未配置日期单列。";
}
async function loadLocations() {
  const selectedTerm = $("term").value;
  const data = await api("/api/locations?" + new URLSearchParams({term: selectedTerm}));
  if ($("term").value !== selectedTerm) return;
  state.locations = data.locations;
  const previous = $("building").value;
  $("building").replaceChildren(new Option("全部教学楼", ""));
  for (const item of [...new Set(data.locations.map((r) => r.building))]) $("building").add(new Option(item, item));
  if ([...$("building").options].some((o) => o.value === previous)) $("building").value = previous;
  roomOptions();
}
function roomOptions() {
  const previous = $("room").value;
  const list = state.locations.filter((r) => !$("building").value || r.building === $("building").value);
  $("room").replaceChildren(new Option(list.length ? "全部教室" : "暂无教室数据", ""),
    ...list.map((r) => new Option(r.room, r.room)));
  if (list.some((r) => r.room === previous)) $("room").value = previous;
  $("room").disabled = list.length === 0;
}
async function refreshMeta(initial = false) {
  const data = await api("/api/meta");
  state.meta = data;
  $("stat-lessons").textContent = number(data.totals.lessons);
  $("stat-rooms").textContent = number(data.totals.rooms);
  $("stat-days").textContent = number(data.coverage.days);
  $("stat-dates").textContent = data.totals.first_date ? data.totals.first_date + " — " + data.totals.last_date : "尚未导入";
  $("today-label").textContent = data.today + " · 北京时间";
  const previous = initial ? urlState.get("term") : $("term").value;
  $("term").replaceChildren(new Option("全部学期", ""));
  const options = [...data.calendar.semesters].sort((a,b) => b.order-a.order);
  for (const term of options) $("term").add(new Option(term.label, term.id));
  if (data.totals.unknown_terms) $("term").add(new Option("非教学期／校历待配置", "unknown"));
  if (previous !== null && previous !== undefined && [...$("term").options].some((x) => x.value === previous)) $("term").value = previous;
  else {
    const target = initial && urlState.get("date") ? urlState.get("date") : data.today;
    const matching = options.find((x) => x.start <= target && target <= x.end);
    $("term").value = matching?.id || "";
  }
  if (initial) {
    $("date").value = urlState.get("date") || data.today;
    $("mode").value = urlState.get("mode") || "all";
    if (!$("mode").value) $("mode").value = "all";
    for (const [name, id] of [["time","time"],["start","start"],["end","end"],["period_from","period-from"],["period_to","period-to"]]) {
      if (urlState.has(name)) $(id).value = urlState.get(name);
    }
  }
  updateTermNote();
  await loadLocations();
  if (initial) {
    const requestedBuilding = urlState.get("building") || "";
    if ([...$("building").options].some((o) => o.value === requestedBuilding)) {
      $("building").value = requestedBuilding;
    }
    roomOptions();
    const requestedRoom = urlState.get("room") || "";
    if ([...$("room").options].some((o) => o.value === requestedRoom)) $("room").value = requestedRoom;
  }
}
function renderRows(data) {
  $("results").replaceChildren();
  for (const row of data.lessons) {
    const card = element("article", "course-card");
    const place = element("div", "card-room", row.room_number || row.room);
    place.append(element("small", "", row.building));
    const body = element("div", "card-body");
    body.append(element("h3", "", row.title));
    const meta = element("div", "card-meta");
    meta.append(element("span", "", row.teacher || "教师未提供"), element("span", "", row.department || "院系未提供"));
    body.append(meta, element("div", "card-term", row.semester + " · " + row.lesson_date));
    const times = element("div", "card-time");
    times.append(element("strong", "", periodLabel(row.periods)),
      element("span", "", row.times[0].start + " – " + row.times.at(-1).end),
      element("small", "", "仅节次内为上课时间"));
    card.append(place, body, times); $("results").append(card);
  }
  if (!data.lessons.length) {
    const empty = element("div", "empty");
    empty.append(element("strong", "", data.coverage ? "未找到符合条件的课程" : "这个日期还没有导入课表"),
      element("p", "", data.coverage ? "试试其他教室或时段。没有课程记录不代表教室空闲。" : "可同步所选日期，或查看已有数据的日期。"));
    if (!data.coverage && state.meta.totals.last_date) {
      const recent = element("button", "ghost", "查看最近入库日期 " + state.meta.totals.last_date);
      recent.addEventListener("click", () => { $("date").value = state.meta.totals.last_date; chooseDateTerm(); search(); });
      empty.append(recent);
    }
    $("results").append(empty);
  }
}
function renderNotice(data) {
  const notices = [];
  const term = $("term").value;
  if (!data.coverage) notices.push("所选日期尚未入库，本次结果不能用于判断教室是否有课。");
  else {
    const audit = data.coverage.excluded;
    notices.push("当日已导入 " + data.coverage.accepted_count + " 条有效课次，剔除 " + (audit.placeholder_room || 0) + " 条默认或空教室记录。");
    if (audit.unrecognized_period) notices.push(audit.unrecognized_period + " 条节次无法识别，未参与时段查询。");
  }
  if (term && data.date_terms.length && !data.date_terms.some((t) => t.term_id === term)) notices.push("所选日期不属于当前筛选学期，请调整学期或日期。");
  if (term === "unknown") notices.push("这些日期不在已配置的教学期范围内；未按课程原始学期字段推断。");
  message("notice", notices.join(" "));
}
async function search(page = 1) {
  const seq = ++state.sequence;
  state.page = page;
  const params = new URLSearchParams(new FormData($("search-form")));
  params.set("page", String(page));
  $("search").disabled = true; $("results-area").setAttribute("aria-busy", "true");
  message("error", ""); modeChanged();
  try {
    const data = await api("/api/search?" + params);
    if (seq !== state.sequence) return;
    state.response = data;
    history.replaceState(null, "", "/?" + params);
    $("result-count").textContent = number(data.total) + " 课次";
    $("result-caption").textContent = $("date").value + " · " + ($("building").value || "全部教学楼") + " · " + ($("room").value || "全部教室");
    renderNotice(data); renderRows(data);
    const pages = Math.max(1, Math.ceil(data.total/data.page_size));
    $("pagination").hidden = pages <= 1;
    $("page-label").textContent = page + " / " + pages;
    $("previous-page").disabled = page <= 1; $("next-page").disabled = page >= pages;
  } catch (error) {
    if (seq !== state.sequence) return;
    message("error", error.message); $("results").replaceChildren(); $("result-count").textContent = "—"; $("pagination").hidden = true;
  } finally {
    if (seq === state.sequence) { $("search").disabled = false; $("results-area").setAttribute("aria-busy", "false"); }
  }
}
function chooseDateTerm() {
  const date = $("date").value;
  const term = state.meta.calendar.semesters.find((x) => x.start <= date && date <= x.end);
  $("term").value = term?.id || (state.meta.totals.unknown_terms ? "unknown" : "");
  updateTermNote(); loadLocations().catch((e) => message("error", e.message));
}
async function sync() {
  if (state.syncing) return;
  state.syncing = true; $("sync").disabled = true;
  const date = $("date").value;
  $("sync-message").textContent = "正在同步 " + date + "…";
  try {
    const job = await api("/api/sync", {method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify({date})});
    let done = false;
    while (!done) {
      await new Promise((resolve) => setTimeout(resolve, 1000));
      const status = await api("/api/job?" + new URLSearchParams({id:job.id}));
      $("sync-message").textContent = date + " · " + status.message;
      if (status.status === "failed") throw new Error(status.message);
      if (status.status === "done") {
        done = true; await refreshMeta();
        $("sync-message").textContent = date + " 已同步：" + status.result.accepted + " 条有效课次，" + (status.result.excluded.placeholder_room || 0) + " 条默认教室已舍弃。";
        await search();
      }
    }
  } catch (error) { $("sync-message").textContent = "同步未完成：" + error.message + " 原数据保留。"; }
  finally { state.syncing = false; $("sync").disabled = false; }
}
function renderAuth(data) {
  const busy = ["opening", "verifying", "logging_out"].includes(data.status);
  $("auth-message").textContent = data.status === "idle" && data.auth.saved ? data.auth.message : data.message;
  for (const id of ["auth-login", "auth-complete", "auth-logout"]) $(id).disabled = busy;
  return busy;
}
async function authAction(action) {
  for (const id of ["auth-login", "auth-complete", "auth-logout"]) $(id).disabled = true;
  try {
    let data = await api("/api/auth/" + action, {method:"POST", headers:{"Content-Type":"application/json"}, body:"{}"});
    while (renderAuth(data)) {
      await new Promise((resolve) => setTimeout(resolve, 1000));
      data = await api("/api/auth/status");
    }
  } catch (error) {
    $("auth-message").textContent = error.message;
  } finally {
    for (const id of ["auth-login", "auth-complete", "auth-logout"]) $(id).disabled = false;
  }
}
async function init() {
  for (const [id, action] of [["auth-login", "login"], ["auth-complete", "complete"], ["auth-logout", "logout"]]) {
    $(id).addEventListener("click", () => authAction(action));
  }
  api("/api/auth/status").then(renderAuth).catch((error) => {$("auth-message").textContent = error.message;});
  $("search-form").addEventListener("submit", (e) => {e.preventDefault(); search();});
  $("mode").addEventListener("change", modeChanged);
  $("period-from").addEventListener("change", () => {if (+$("period-to").value < +$("period-from").value) $("period-to").value = $("period-from").value; modeChanged();});
  $("period-to").addEventListener("change", modeChanged);
  $("building").addEventListener("change", () => { roomOptions(); search(); });
  $("room").addEventListener("change", () => search());
  $("date").addEventListener("change", chooseDateTerm);
  $("term").addEventListener("change", async () => {
    updateTermNote();
    const term = state.meta.calendar.semesters.find((x) => x.id === $("term").value);
    if (term && ($("date").value < term.start || $("date").value > term.end)) {
      const populated = state.meta.terms.find((t) => t.id === term.id);
      $("date").value = populated?.last_date || term.start;
    }
    try { await loadLocations(); await search(); } catch(e) { message("error", e.message); }
  });
  for (const [id, offset] of [["previous-day",-1],["next-day",1]]) $(id).addEventListener("click", () => {
    const day = new Date($("date").value + "T12:00:00+08:00");
    day.setUTCDate(day.getUTCDate()+offset); $("date").value = day.toISOString().slice(0,10); chooseDateTerm(); search();
  });
  $("previous-page").addEventListener("click", () => search(state.page-1));
  $("next-page").addEventListener("click", () => search(state.page+1));
  $("all-day").addEventListener("click", () => {$("mode").value="all"; search();});
  $("now").addEventListener("click", () => {
    const parts = Object.fromEntries(new Intl.DateTimeFormat("en-CA",{timeZone:"Asia/Shanghai",year:"numeric",month:"2-digit",day:"2-digit",hour:"2-digit",minute:"2-digit",hourCycle:"h23"}).formatToParts(new Date()).map((p) => [p.type,p.value]));
    $("date").value = parts.year + "-" + parts.month + "-" + parts.day; $("time").value = parts.hour + ":" + parts.minute;
    $("mode").value="time"; chooseDateTerm(); search();
  });
  $("sync").addEventListener("click", sync);
  try {
    const meta = await api("/api/meta");
    for (const p of meta.periods) {
      $("period-from").add(new Option("第 " + p.number + " 节", p.number));
      $("period-to").add(new Option("第 " + p.number + " 节", p.number));
      const chip = element("button","period-chip","第 " + p.number + " 节"); chip.type="button"; chip.dataset.number=p.number;
      chip.append(element("small","",p.start + "–" + p.end));
      chip.addEventListener("click",() => {$("mode").value="period";$("period-from").value=p.number;$("period-to").value=p.number;search();});
      $("periods").append(chip);
    }
    await refreshMeta(true); modeChanged(); await search();
  } catch (error) { message("error",error.message); }
}
init();
