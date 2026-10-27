// @ts-check
const { test, expect } = require("@playwright/test");

test.beforeEach(async ({ page }) => {
  await page.goto("/");
});

test("shopper can switch user, consent, chat, and see the memory panel", async ({ page }) => {
  await expect(page.getByRole("button", { name: "Maya" })).toBeVisible();

  await page.getByRole("button", { name: "Maya" }).click();
  await expect(page.getByRole("dialog")).toBeVisible();
  await page.getByRole("button", { name: "Yes, remember me" }).click();
  await expect(page.getByRole("dialog")).toBeHidden();

  await page.getByLabel("Message").fill("Something for a French press under $20?");
  await page.getByRole("button", { name: "Send" }).click();

  // Live LLM call -- same free-tier latency/flakiness noted in SESSION_LOG.md, so a generous
  // timeout rather than a tight one.
  await expect(page.locator(".bubble.assistant").last()).toBeVisible({ timeout: 25_000 });

  const panel = page.getByRole("complementary", { name: "What I remember about you" });
  await expect(panel.getByRole("button", { name: "Forget everything" })).toBeVisible();
  await expect(panel.getByRole("link", { name: "Download my data" })).toBeVisible();

  // FR-7 governance (S6): "Forget everything" is a hard delete -- confirm it actually empties
  // the panel instead of just trusting a success toast.
  await panel.getByRole("button", { name: "Forget everything" }).click();
  await expect(panel.getByText("Forget everything: done.")).toBeVisible();
  await expect(panel.getByText("Nothing remembered yet.")).toBeVisible();

  // Consent withdraw toggle (design brief §11): existing data untouched, just confirms.
  await panel.getByRole("button", { name: "Withdraw consent" }).click();
  await expect(panel.getByText(/Consent withdrawn/)).toBeVisible();
});

test("declining consent skips the memory panel", async ({ page }) => {
  await page.getByRole("button", { name: "Leo" }).click();
  await page.getByRole("button", { name: "No thanks" }).click();
  await expect(page.getByRole("complementary", { name: "What I remember about you" })).toHaveCount(0);
});

test("ops dashboard shows aggregate counts, no memory content", async ({ page }) => {
  await page.getByRole("link", { name: "Ops dashboard" }).click();
  await expect(page.getByText("Memory writes")).toBeVisible();
  await expect(page.getByText("Blocks by PII type")).toBeVisible();
});
