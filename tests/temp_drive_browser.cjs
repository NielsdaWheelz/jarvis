const assert = require("node:assert/strict");
const { chromium, webkit } = require(process.env.JARVIS_TEST_PLAYWRIGHT);
const origin = process.env.JARVIS_TEST_ORIGIN;
const active = "a".repeat(8) + "-aaaa-aaaa-aaaa-" + "a".repeat(12);

(async () => {
  for (const browserType of [chromium, webkit]) {
    const browser = await browserType.launch({ headless: true });
    for (const viewport of [{ width: 1280, height: 800 }, { width: 390, height: 844 }]) {
      const page = await browser.newPage({ viewport });
      const faults = [];
      page.on("pageerror", error => faults.push(String(error)));
      await page.route(origin + "/api/messages", route => {
        assert.equal(route.request().headers()["x-jarvis-viewer-contract"], "drive-files");
        return route.fulfill({ json: { items: [], next_before: null } });
      });
      await page.route(origin + "/api/workspace/approvals", route => route.fulfill({ json: [] }));
      await page.route(origin + "/api/todos?all=true", route => route.fulfill({ json: { items: [], total: 0, offset: 0 } }));
      await page.request.get(origin + "/fixture/state/normal");
      await page.goto(origin + "/files");
      await page.getByRole("heading", { name: "my drive", exact: true }).waitFor();
      await page.getByRole("heading", { name: "pending uploads" }).waitFor();
      const downloadPath = await page.getByRole("link", { name: "download", exact: true }).getAttribute("href");
      assert.equal(downloadPath, "/api/drive/origin/bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb/content");
      const pending = await page.request.get(origin + downloadPath);
      assert.equal(pending.headers()["cache-control"], "private, no-store, no-transform");
      assert.equal((await pending.body()).subarray(0, 5).toString(), "%PDF-");
      assert.equal((await page.request.get(origin + "/api/files/" + active)).status(), 404);
      assert.equal(await page.getByRole("button", { name: "files", exact: true }).getAttribute("aria-pressed"), "true");
      if (viewport.width < 720) await page.getByRole("button", { name: "open conversation" }).click();
      await page.getByRole("textbox", { name: "message jarvis" }).fill("my unsent draft");
      if (viewport.width < 720) await page.getByRole("button", { name: "close sidebar" }).click();
      await page.getByRole("link", { name: "image.png" }).click();
      const image = page.getByRole("img", { name: "image.png" });
      await image.waitFor();
      assert.equal(await image.evaluate(img => img.complete && img.naturalWidth > 0), true);
      await page.getByRole("button", { name: "back", exact: true }).click();
      await page.getByRole("link", { name: "letter" }).click();
      assert.equal(await page.getByRole("link", { name: "open in drive" }).getAttribute("href"),
        "https://docs.google.com/document/d/letter/edit");
      await page.getByRole("button", { name: "back", exact: true }).click();
      await page.getByRole("link", { name: "tax", exact: true }).click();
      await page.getByRole("link", { name: "2026", exact: true }).click();
      await page.getByRole("link", { name: "tax", exact: true }).waitFor();
      await page.getByRole("button", { name: "attach to chat", exact: true }).click();
      assert.deepEqual(await page.evaluate(() => JSON.parse(sessionStorage.getItem("jarvis.home.draft")).ref),
        { kind: "drive_file", subject: "owner", id: "2026" });
      assert.equal(await page.getByRole("textbox", { name: "message jarvis" }).inputValue(), "my unsent draft");
      await page.getByRole("button", { name: "remove reference" }).click();
      if (viewport.width < 720) await page.getByRole("button", { name: "close sidebar" }).click();
      await page.getByRole("button", { name: "recent", exact: true }).click();
      await page.getByText("tax / 2026").waitFor();
      await page.getByText("shared / accountant").waitFor();
      const returns = page.getByRole("link", { name: "return.pdf" });
      assert.equal(await returns.count(), 2);
      await page.getByRole("button", { name: "more files" }).click();
      await page.getByText(/limiting requests/).waitFor();
      assert.equal(await returns.count(), 2);
      await returns.first().click();
      await page.getByRole("img", { name: "page 1 of 6" }).waitFor();
      await page.getByRole("link", { name: "next page" }).click();
      await page.getByRole("img", { name: "page 2 of 6" }).waitFor();
      await page.getByRole("button", { name: "back", exact: true }).click();
      await page.getByRole("heading", { name: "recent", exact: true }).waitFor();
      await returns.first().waitFor();
      await page.waitForFunction(() => document.activeElement.textContent === "return.pdf");
      await page.getByRole("searchbox", { name: "search filenames" }).fill("return");
      await page.getByRole("button", { name: "search", exact: true }).click();
      await page.getByRole("heading", { name: "search results", exact: true }).waitFor();
      await returns.first().click();
      await page.getByRole("img", { name: "page 1 of 6" }).waitFor();
      await page.getByRole("button", { name: "back", exact: true }).click();
      await page.getByRole("heading", { name: "search results", exact: true }).waitFor();
      assert.equal(await page.getByRole("searchbox").inputValue(), "return");
      await page.goto(origin + "/f/" + active + "?page=6");
      await page.getByRole("img", { name: "page 6 of 6" }).waitFor();
      assert.equal(page.url(), origin + "/files/owner/return?page=6");
      await page.request.get(origin + "/fixture/state/changed");
      await page.reload();
      await page.getByText("page 6 is unavailable in this file.").waitFor();
      await page.getByRole("link", { name: "open page 1" }).click();
      await page.getByRole("img", { name: "page 1 of 5" }).waitFor();
      await page.request.get(origin + "/fixture/state/denied");
      await page.reload();
      await page.getByText("this file is missing or you no longer have access.").waitFor();
      if (viewport.width < 720) await page.getByRole("button", { name: "open conversation" }).click();
      assert.equal(await page.getByRole("textbox", { name: "message jarvis" }).inputValue(), "my unsent draft");
      assert.deepEqual(faults, []);
      console.log(browserType.name(), viewport.width, "pass");
      await page.close();
    }
    await browser.close();
  }
})().catch(error => { console.error(error); process.exit(1); });
