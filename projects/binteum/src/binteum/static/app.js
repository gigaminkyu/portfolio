/* 빈틈(BinTeum) 웹 UI — 프레임워크 없이 동작. 서버 모드와 오프라인 리포트 모드를 같은 코드로 렌더한다. */
(function () {
  "use strict";

  const PRESET = window.__BINTEUM_PRESET__ || null;   // 저장된 실행 결과(오프라인 리포트)
  const META_PRESET = window.__BINTEUM_META__ || null;
  const $ = (sel) => document.querySelector(sel);
  const el = (tag, cls, text) => {
    const node = document.createElement(tag);
    if (cls) node.className = cls;
    if (text !== undefined && text !== null) node.textContent = text;
    return node;
  };

  let META = META_PRESET || { emds: [], spots: [], data: null, scenarios: [] };
  let STATE = { result: null, selected: null, themes: new Set(), view: "cards" };

  const SCENARIOS = {
    family: {
      query: "성산에 있는데 지금 너무 붐벼. 애가 3살이라 오후엔 실내 위주로, 6시까지 숙소 복귀",
      emd: "성산읍", spot: "seongsan-ilchulbong", end_time: "18:00",
      party: "family_kid", mobility: "car", indoor: true, themes: ["가족", "실내"],
    },
    budget: {
      query: "애월에 있는데 버스로 다닐 거고 예산 3만원, 9시까지 야경 보고 싶어",
      emd: "애월읍", spot: "handam-beach", end_time: "21:00",
      party: "couple", mobility: "bus", indoor: false, themes: ["야경", "해변"],
    },
    parents: {
      query: "중문인데 부모님 모시고 있어요. 걷기 힘드셔서 이동 짧게, 5시까지",
      emd: "중문동", spot: "jungmun-beach", end_time: "17:00",
      party: "with_parents", mobility: "car", indoor: false, themes: ["자연"],
    },
  };

  /* ---------------------------------------------------------------- 초기화 */
  async function init() {
    if (PRESET) {
      META = META_PRESET || META;
      fillSelects();
      renderResult(PRESET);
      document.querySelectorAll(".example").forEach((b) => (b.disabled = true));
      $("#run").disabled = true;
      $("#run").textContent = "저장된 실행 결과";
      return;
    }
    try {
      const res = await fetch("/api/meta");
      META = await res.json();
    } catch (err) {
      setBadge("서버 연결 실패", "warn");
    }
    fillSelects();
    renderDataBadge();
    bind();
  }

  function fillSelects() {
    const emdSel = $("#emd");
    (META.emds || []).forEach((emd) => {
      const opt = el("option", null, emd);
      opt.value = emd;
      emdSel.appendChild(opt);
    });
    const spotSel = $("#spot");
    (META.spots || []).forEach((spot) => {
      const opt = el("option", null, `${spot.name} (${spot.emd})`);
      opt.value = spot.id;
      spotSel.appendChild(opt);
    });
  }

  function bind() {
    $("#form").addEventListener("submit", async (event) => {
      event.preventDefault();
      await run();
    });
    document.querySelectorAll("#themes .chip").forEach((chip) => {
      chip.addEventListener("click", () => {
        const theme = chip.dataset.theme;
        if (STATE.themes.has(theme)) STATE.themes.delete(theme);
        else STATE.themes.add(theme);
        chip.classList.toggle("on", STATE.themes.has(theme));
      });
    });
    document.querySelectorAll(".example").forEach((btn) => {
      btn.addEventListener("click", () => {
        applyScenario(btn.dataset.scenario);
        run();
      });
    });
    $("#emd").addEventListener("change", () => { $("#spot").value = ""; });
  }

  function applyScenario(key) {
    const sc = SCENARIOS[key];
    if (!sc) return;
    $("#query").value = sc.query;
    $("#emd").value = sc.emd;
    $("#end_time").value = sc.end_time;
    $("#party").value = sc.party;
    $("#mobility").value = sc.mobility;
    $("#indoor").checked = !!sc.indoor;
    $("#budget").value = "";
    STATE.themes = new Set(sc.themes || []);
    document.querySelectorAll("#themes .chip").forEach((chip) => {
      chip.classList.toggle("on", STATE.themes.has(chip.dataset.theme));
    });
  }

  /* ---------------------------------------------------------------- 실행 */
  async function run() {
    const body = {
      query: $("#query").value.trim(),
      emd: $("#emd").value,
      spot_id: $("#spot").value,
      end_time: $("#end_time").value,
      party: $("#party").value,
      mobility: $("#mobility").value,
      indoor: $("#indoor").checked,
      budget: $("#budget").value ? Number($("#budget").value) : null,
      themes: Array.from(STATE.themes),
    };
    if (!body.emd && !body.query) {
      toast("현재 위치(읍면동)를 고르거나 상황을 한 줄 적어 주세요");
      return;
    }
    $("#run").disabled = true;
    $("#run").textContent = "계산 중…";
    $("#results").replaceChildren(
      (() => {
        const box = el("div", "loading");
        box.appendChild(el("h2", null, "에이전트가 계산하고 있습니다"));
        const steps = el("ol");
        ["Router · 제약 추출", "Data · 허브/스냅샷 로딩", "Index · 혼잡지수 계산",
          "Planner · 동선 3안", "Critic · 규칙 검증", "Reporter · 근거 정리"].forEach((s) => {
          const li = el("li", null, s);
          box.appendChild(li);
        });
        box.appendChild(el("p", "hint", "보통 1초 안에 끝납니다."));
        return box;
      })()
    );
    try {
      const res = await fetch("/api/plan", {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
      });
      const payload = await res.json();
      renderResult(payload);
    } catch (err) {
      const box = el("div", "empty");
      box.appendChild(el("h2", null, "요청을 처리하지 못했습니다"));
      box.appendChild(el("p", null, String(err)));
      $("#results").replaceChildren(box);
    } finally {
      $("#run").disabled = false;
      $("#run").textContent = "빈틈 찾기";
    }
  }

  /* ---------------------------------------------------------------- 상태 배지 */
  function setBadge(text, kind) {
    const badge = $("#data-badge");
    badge.textContent = text;
    badge.className = "badge badge-" + (kind || "wait");
  }

  function renderDataBadge(data) {
    data = data || (META && META.data);
    if (!data) { setBadge("데이터 확인 중…", "wait"); return; }
    const map = {
      live: ["실시간 허브 API", "live"],
      collected: ["실측 수집 데이터", "live"],
      mixed: ["실측 + 일부 스냅샷", "warn"],
      snapshot: ["동봉 데모 스냅샷", "warn"],
      empty: ["데이터 없음", "warn"],
    };
    const [label, kind] = map[data.mode] || ["상태 미확인", "wait"];
    setBadge(label, kind);
    const ds = data.datasets || [];
    const allSynthetic = ds.length > 0 && ds.every((d) => (d.source_note || "").includes("synthetic-demo"));
    const someSynthetic = ds.some((d) => (d.source_note || "").includes("synthetic-demo"));
    $("#data-date").textContent =
      (data.today ? "기준일 " + data.today : "") +
      (allSynthetic ? " · 합성 데모 데이터" : someSynthetic ? " · 일부 합성" : "");
  }

  /* ---------------------------------------------------------------- 렌더 */
  function renderResult(payload) {
    STATE.result = payload;
    STATE.selected = (payload.summary && payload.summary.best_plan) || (payload.plans && payload.plans[0] && payload.plans[0].key);
    renderDataBadge(payload.data);
    const root = $("#results");
    root.replaceChildren();

    if (payload.error) {
      const box = el("div", "empty");
      box.appendChild(el("h2", null, "요청을 처리하지 못했습니다"));
      box.appendChild(el("p", null, String(payload.error)));
      root.appendChild(box);
      return;
    }
    if (payload.status === "needs_input") {
      const box = el("div", "empty");
      box.appendChild(el("h2", null, payload.message || "위치를 알려주세요"));
      box.appendChild(el("p", null, "읍면동을 고르면 나머지는 기본값으로 계산합니다."));
      root.appendChild(box);
      return;
    }
    if (!payload.ok && payload.status === "no_data") {
      const box = el("div", "empty");
      box.appendChild(el("h2", null, "데이터가 없습니다"));
      (payload.notes || []).forEach((n) => box.appendChild(el("p", null, n)));
      root.appendChild(box);
      return;
    }

    root.appendChild(renderSummary(payload));
    root.appendChild(renderPlans(payload));
    root.appendChild(renderMap(payload));
    root.appendChild(renderDetail(payload));
    root.appendChild(renderActions(payload));
  }

  function renderSummary(payload) {
    const wrap = el("div", "summary");
    const s = payload.summary || {};
    const c = payload.constraints || {};
    const stat = (k, v, small) => {
      const box = el("div", "stat");
      box.appendChild(el("div", "k", k));
      const value = el("div", "v", v === null || v === undefined ? "-" : String(v));
      if (small) value.appendChild(el("small", null, " " + small));
      box.appendChild(value);
      return box;
    };
    wrap.appendChild(stat("추천 동선", s.stops || 0, "곳"));
    wrap.appendChild(stat("평균 혼잡지수", s.avg_ci === null || s.avg_ci === undefined ? "-" : s.avg_ci));
    wrap.appendChild(stat("총 이동", s.travel_min || 0, "분"));
    wrap.appendChild(stat("Critic 반려", s.critic_rounds || 0, "회"));
    wrap.appendChild(stat("응답", payload.elapsed_ms || 0, "ms"));

    const box = el("div", "constraints");
    box.appendChild(el("div", "k", "해석된 제약 (Router)"));
    const row = el("div", "row");
    const add = (text, cls) => row.appendChild(el("span", "tag" + (cls ? " " + cls : ""), text));
    if (c.origin_emd) add("현재 " + c.origin_emd);
    if (c.end_time) add(c.end_time + "까지");
    add({ solo: "혼자", couple: "커플", family_kid: "아이 동반", with_parents: "부모님", friends: "일행" }[c.party] || c.party);
    add({ car: "렌터카", bus: "버스", walk: "도보" }[c.mobility] || c.mobility);
    if (c.indoor_required) add("실내 위주");
    if (c.budget_krw) add("예산 " + c.budget_krw.toLocaleString() + "원");
    (c.themes || []).forEach((t) => add("#" + t));
    (c.assumptions || []).forEach((a) => add("가정: " + a, "assume"));
    box.appendChild(row);
    const cmp = s.comparisons && s.comparisons[0];
    if (cmp) {
      const line = el("div", "cmp");
      line.appendChild(el("span", null, `${cmp.spot} 지금 추정 CI ${cmp.ci_now}`));
      line.appendChild(el("span", null, `1시간 뒤 추정 CI ${cmp.ci_next_hour}`));
      line.appendChild(el("span", null, "시간대 가정 곡선 적용(추정)"));
      box.appendChild(line);
    }
    wrap.appendChild(box);
    return wrap;
  }

  function renderPlans(payload) {
    const grid = el("div", "plans");
    const best = (payload.summary || {}).best_plan;
    (payload.plans || []).forEach((plan) => {
      const card = el("div", "plan" + (plan.key === best ? " best" : ""));
      const head = el("div", "plan-head");
      const name = el("div", "name");
      name.appendChild(el("span", null, plan.label));
      if (plan.key === best) name.appendChild(el("span", "best-flag", "추천"));
      head.appendChild(name);
      head.appendChild(el("div", "head", plan.headline));
      card.appendChild(head);

      const stops = el("div", "stops");
      if (!plan.stops.length) {
        stops.appendChild(el("div", "stop", "조건을 만족하는 후보가 없습니다."));
      }
      plan.stops.forEach((stop) => {
        const box = el("div", "stop");
        const top = el("div", "stop-top");
        const left = el("div");
        left.appendChild(el("div", "stop-name", `${stop.order}. ${stop.spot_name}`));
        left.appendChild(el("div", "stop-meta",
          `${stop.arrive}~${stop.depart} · ${stop.dwell_min}분 · 이동 ${stop.travel_min}분(${stop.travel_km}km)`));
        top.appendChild(left);

        const ciClass = stop.ci >= 70 ? "high" : stop.ci >= 45 ? "mid" : "low";
        const ciBox = el("div", "ci " + ciClass);
        ciBox.appendChild(el("div", "num", String(stop.ci)));
        ciBox.appendChild(el("div", "lab", stop.ci_label));
        top.appendChild(ciBox);
        box.appendChild(top);

        const bar = el("div", "bar " + ciClass);
        const fill = el("i");
        fill.style.width = Math.max(2, Math.min(100, stop.ci)) + "%";
        fill.style.background = "currentColor";
        bar.style.color = `var(--${ciClass === "high" ? "red" : ciClass === "mid" ? "amber" : "green"})`;
        bar.appendChild(fill);
        box.appendChild(bar);

        const why = el("ul", "why");
        (stop.why || []).slice(0, 4).forEach((w) => why.appendChild(el("li", null, w)));
        box.appendChild(why);
        stops.appendChild(box);
      });
      card.appendChild(stops);
      (plan.warnings || []).forEach((w) => card.appendChild(el("div", "warn", w)));
      grid.appendChild(card);
    });
    return grid;
  }

  /* ---------------------------------------------------------------- 지도(SVG, 타일 불필요) */
  var ISLAND = [
    [126.530, 33.515], [126.580, 33.525], [126.620, 33.532], [126.670, 33.545],
    [126.720, 33.552], [126.760, 33.550], [126.800, 33.540], [126.850, 33.532],
    [126.890, 33.510], [126.930, 33.480], [126.945, 33.455], [126.930, 33.415],
    [126.890, 33.375], [126.850, 33.345], [126.820, 33.320], [126.780, 33.300],
    [126.730, 33.270], [126.680, 33.255], [126.630, 33.248], [126.580, 33.240],
    [126.545, 33.236], [126.500, 33.235], [126.450, 33.232], [126.410, 33.238],
    [126.360, 33.225], [126.320, 33.215], [126.280, 33.212], [126.245, 33.213],
    [126.210, 33.225], [126.175, 33.250], [126.165, 33.290], [126.155, 33.330],
    [126.170, 33.360], [126.195, 33.390], [126.225, 33.415], [126.255, 33.440],
    [126.290, 33.462], [126.330, 33.470], [126.380, 33.480], [126.430, 33.495],
    [126.470, 33.505], [126.500, 33.512]
  ];
  var BOUNDS = { lon0: 126.14, lon1: 126.96, lat0: 33.10, lat1: 33.57 };

  var VIEW = BOUNDS;

  function project(lon, lat, w, h) {
    var x = ((lon - VIEW.lon0) / (VIEW.lon1 - VIEW.lon0)) * w;
    var y = ((VIEW.lat1 - lat) / (VIEW.lat1 - VIEW.lat0)) * h;
    return [x, y];
  }

  var MAP_W = 900, MAP_H = 340;

  function fitView(coords) {
    if (!coords || coords.length < 2) return BOUNDS;
    var lons = coords.map(function (c) { return c[0]; });
    var lats = coords.map(function (c) { return c[1]; });
    var pad = 0.035;
    var lon0 = Math.min.apply(null, lons) - pad;
    var lon1 = Math.max.apply(null, lons) + pad;
    var lat0 = Math.min.apply(null, lats) - pad * 0.75;
    var lat1 = Math.max.apply(null, lats) + pad * 0.75;
    var minSpan = 0.14;
    if (lon1 - lon0 < minSpan) { var cx = (lon0 + lon1) / 2; lon0 = cx - minSpan / 2; lon1 = cx + minSpan / 2; }
    if (lat1 - lat0 < minSpan * 0.62) { var cy = (lat0 + lat1) / 2; lat0 = cy - minSpan * 0.31; lat1 = cy + minSpan * 0.31; }
    // 제주 위도(33.36°)에서 경도 1도 ≈ 위도 1도×cos(위도) 이므로, 화면비에 맞춰
    // 위도 폭을 다시 잡아 섬 모양이 납작해지지 않게 한다(등방 투영).
    var cosLat = Math.cos(33.36 * Math.PI / 180);
    var wantLat = (lon1 - lon0) * cosLat * (MAP_H / MAP_W);
    if (lat1 - lat0 < wantLat) {
      var cy2 = (lat0 + lat1) / 2;
      lat0 = cy2 - wantLat / 2; lat1 = cy2 + wantLat / 2;
    }
    return { lon0: lon0, lon1: lon1, lat0: lat0, lat1: lat1 };
  }

  function svgNode(name, attrs) {
    var node = document.createElementNS("http://www.w3.org/2000/svg", name);
    Object.entries(attrs || {}).forEach(function (entry) { node.setAttribute(entry[0], entry[1]); });
    return node;
  }

  function renderMap(payload) {
    var wrap = el("div", "mapbox");
    var plan = (payload.plans || []).find(function (p) { return p.key === STATE.selected; }) || (payload.plans || [])[0];
    wrap.appendChild(el("h3", null, "동선 지도 — " + (plan ? plan.label : "")));
    wrap.appendChild(el("div", "sub", "좌표 기반 도식(타일·지도 API 불필요, 오프라인 동작). 동선에 맞춰 자동 확대됩니다."));
    var W = MAP_W, H = MAP_H;
    var byId = {};
    (META.spots || []).forEach(function (s) { byId[s.id] = s; });
    var origin = byId[(payload.constraints || {}).origin_spot];

    var coords = [];
    if (origin) coords.push([origin.lon, origin.lat]);
    (plan ? plan.stops : []).forEach(function (stop) {
      if (byId[stop.spot_id]) coords.push([byId[stop.spot_id].lon, byId[stop.spot_id].lat]);
    });
    VIEW = fitView(coords);

    var svg = svgNode("svg", { class: "map", viewBox: "0 0 " + W + " " + H });
    svg.appendChild(svgNode("polygon", {
      class: "island",
      points: ISLAND.map(function (pt) { return project(pt[0], pt[1], W, H).join(","); }).join(" ")
    }));

    var points = coords.map(function (c) { return project(c[0], c[1], W, H); });
    if (points.length > 1) {
      svg.appendChild(svgNode("polyline", {
        class: "route", points: points.map(function (p) { return p.join(","); }).join(" ")
      }));
    }
    (plan ? plan.stops : []).forEach(function (stop, idx) {
      var meta = byId[stop.spot_id];
      if (!meta) return;
      var p = project(meta.lon, meta.lat, W, H);
      svg.appendChild(svgNode("circle", { class: "dot" + (stop.indoor ? " indoor" : ""),
        cx: p[0], cy: p[1], r: 9 }));
      var num = svgNode("text", { x: p[0], y: p[1] + 3, "text-anchor": "middle", class: "num" });
      num.textContent = String(idx + 1);
      svg.appendChild(num);
      var right = p[0] < W * 0.68;
      var label = svgNode("text", {
        x: right ? p[0] + 13 : p[0] - 13,
        y: p[1] + 3 + (idx % 2 === 0 ? -11 : 11),
        class: "lbl", "text-anchor": right ? "start" : "end"
      });
      label.textContent = stop.spot_name;
      svg.appendChild(label);
    });
    if (origin) {
      var op = project(origin.lon, origin.lat, W, H);
      svg.appendChild(svgNode("circle", { class: "dot", cx: op[0], cy: op[1], r: 5,
        fill: "#c47f17", stroke: "#fff" }));
      var olabel = svgNode("text", { x: op[0], y: op[1] - 12, class: "lbl", "text-anchor": "middle" });
      olabel.textContent = "출발";
      svg.appendChild(olabel);
    }
    wrap.appendChild(svg);
    return wrap;
  }

  function renderDetail(payload) {
    const plan = (payload.plans || []).find((p) => p.key === STATE.selected) || (payload.plans || [])[0];
    const wrap = el("div", "detail");
    wrap.appendChild(el("h3", null, "근거 상세 — 데이터 ID · 기준일 · 수치"));
    if (!plan) return wrap;

    const table = el("table");
    const thead = el("tr");
    ["#", "장소", "CI", "사용 항(가중치)", "제외 항", "기준일", "신뢰도"].forEach((h) =>
      thead.appendChild(el("th", null, h))
    );
    table.appendChild(thead);
    plan.stops.forEach((stop) => {
      const tr = el("tr");
      tr.appendChild(el("td", null, String(stop.order)));
      tr.appendChild(el("td", null, stop.spot_name));
      tr.appendChild(el("td", null, `${stop.ci} (${stop.ci_label})`));
      const terms = stop.evidence.terms || {};
      const weights = stop.evidence.weights || {};
      tr.appendChild(el("td", null,
        Object.entries(terms).filter(([, v]) => v !== null)
          .map(([k, v]) => `${k} ${(v * 100).toFixed(0)}%`).join(" · ") || "-"));
      tr.appendChild(el("td", null, (stop.evidence.dropped_terms || []).join(", ") || "없음"));
      tr.appendChild(el("td", null, stop.evidence.base_date || ""));
      tr.appendChild(el("td", null, stop.evidence.confidence || ""));
      table.appendChild(tr);
    });
    wrap.appendChild(table);

    const dl = el("div", "actions");
    (payload.data && payload.data.datasets ? payload.data.datasets : []).forEach((d) => {
      const chip = el("span", "tag",
        `id=${d.hub_id} ${d.dataset} · ${d.mode} · ${d.rows}행`);
      dl.appendChild(chip);
    });
    wrap.appendChild(dl);

    if (payload.notes && payload.notes.length) {
      const notes = el("ul", "notes");
      payload.notes.forEach((n) => notes.appendChild(el("li", null, n)));
      wrap.appendChild(notes);
    }
    return wrap;
  }

  function renderActions(payload) {
    const wrap = el("div", "actions");
    const copy = el("button", "ghost", "카톡 공유용 텍스트 복사");
    copy.addEventListener("click", async () => {
      const text = shareText(payload);
      try {
        await navigator.clipboard.writeText(text);
        toast("복사했습니다");
      } catch (err) {
        window.prompt("복사할 텍스트", text);
      }
    });
    wrap.appendChild(copy);

    const json = el("button", "ghost", "결과 JSON 내려받기");
    json.addEventListener("click", () => {
      const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = (payload.run_id || "binteum") + ".json";
      a.click();
    });
    wrap.appendChild(json);

    if (payload.outputs && payload.outputs.html) {
      const info = el("span", "tag", "리포트: " + payload.outputs.html.split("/").pop());
      wrap.appendChild(info);
    }
    return wrap;
  }

  function shareText(payload) {
    const c = payload.constraints || {};
    const plan = (payload.plans || []).find((p) => p.key === STATE.selected) || (payload.plans || [])[0];
    const lines = [];
    lines.push(`[빈틈] ${c.origin_emd || ""} · ${c.end_time}까지 · ${plan ? plan.label : ""}`);
    if (!plan) return lines.join("\n");
    plan.stops.forEach((stop) => {
      lines.push(`${stop.order}. ${stop.arrive} ${stop.spot_name} — CI ${stop.ci}(${stop.ci_label}), ${stop.dwell_min}분`);
    });
    lines.push(`이동 ${plan.totals.travel_min}분 · 평균 CI ${plan.totals.avg_ci}`);
    const ds = payload.data && payload.data.datasets ? payload.data.datasets : [];
    lines.push("근거: " + ds.map((d) => `${d.dataset}(${d.mode})`).join(", "));
    return lines.join("\n");
  }

  let toastTimer = null;
  function toast(message) {
    let node = document.querySelector(".toast");
    if (!node) {
      node = el("div", "toast");
      document.body.appendChild(node);
    }
    node.textContent = message;
    node.classList.add("on");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => node.classList.remove("on"), 1800);
  }

  document.addEventListener("DOMContentLoaded", init);
})();
