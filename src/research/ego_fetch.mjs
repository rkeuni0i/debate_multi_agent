// 2단계: 선별된 후보만 ego-browser로 확인한다.
//  - url이 있으면: 페이지를 열어 제목/DOI/초록/수치 포함 문장을 발췌한다.
//  - url이 없고 query만 있으면: 검색 결과 상위 링크를 수집한다(자동으로 열지는 않는다. 사람이 고른 뒤 url로 다시 실행).
// 입력/출력 경로는 진입점에서 globalThis.EGO_IN / EGO_OUT 으로 전달된다(환경변수는 ego 프로세스에 전달되지 않음).
import fs from "node:fs";

const input = JSON.parse(fs.readFileSync(globalThis.EGO_IN, "utf-8"));
const task = await taskSpace("evidence source check");
const page = task.page("p1");
const results = [];

for (const item of input) {
  try {
    if (item.url) {
      await page.goto(item.url);
      const data = await page.evaluate(() => {
        const meta = (n) =>
          document.querySelector(`meta[name="${n}"],meta[property="${n}"]`)?.content || "";
        const body = document.body?.innerText || "";
        const sentences = body.split(/(?<=[.!?。])\s+/);
        const withNumbers = sentences.filter((s) => /\d+(\.\d+)?\s?(%|%p|만 개|percent)/.test(s));
        return {
          title: document.title,
          citation_title: meta("citation_title") || meta("og:title"),
          citation_doi: meta("citation_doi"),
          abstract: meta("citation_abstract") || meta("description") || meta("og:description"),
          number_sentences: withNumbers.slice(0, 15),
          body_head: body.slice(0, 1500),
        };
      });
      results.push({ ...item, mode: "fetch", ok: true, ...data });
    } else {
      await page.goto("https://www.google.com/search?q=" + encodeURIComponent(item.query) + "&hl=ko");
      const links = await page.evaluate(() => {
        const out = [];
        for (const h of document.querySelectorAll("a h3")) {
          const a = h.closest("a");
          if (a && a.href && !out.some((o) => o.url === a.href)) out.push({ title: h.innerText, url: a.href });
        }
        return out.slice(0, 5);
      });
      results.push({ ...item, mode: "search", ok: links.length > 0, links });
    }
  } catch (e) {
    results.push({ ...item, ok: false, error: String(e).slice(0, 300) });
  }
}

// 결과는 finish 전에 먼저 저장한다 (finish 단계에서 SDK 오류가 나도 데이터는 보존된다).
fs.writeFileSync(globalThis.EGO_OUT, JSON.stringify(results, null, 2), "utf-8");
console.log(`done: ${results.filter((r) => r.ok).length}/${results.length} ok`);

try {
  await task.finish({ keep: [] });
} catch (e) {
  // ego-browser 0.6.2.5: finish 직후 SDK가 종료된 task space로 명령을 보내 오류가 난다. 결과 저장은 끝난 상태.
  console.log("[ego_fetch] finish 단계 경고(무시):", String(e).split("\n")[0]);
}
