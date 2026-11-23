const { chromium } = require('playwright');
const path = require('path');
const fs = require('fs');

(async () => {
  const root = __dirname;
  const html = path.join(root, 'LTC_Skill落地评估.html');
  const outputDir = path.join(root, 'rendered');
  fs.mkdirSync(outputDir, { recursive: true });

  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage({ viewport: { width: 1920, height: 1080 }, deviceScaleFactor: 1 });
  await page.goto(`file://${html}`);
  await page.waitForTimeout(400);

  const count = await page.locator('.slide').count();
  for (let i = 0; i < count; i += 1) {
    await page.evaluate(index => {
      const slides = [...document.querySelectorAll('.slide')];
      slides.forEach((slide, idx) => slide.classList.toggle('active', idx === index));
      document.querySelector('.nav').style.display = 'none';
    }, i);
    await page.screenshot({
      path: path.join(outputDir, `slide-${String(i + 1).padStart(2, '0')}.png`),
      fullPage: false
    });
  }

  const contact = await browser.newPage({ viewport: { width: 1920, height: 1080 }, deviceScaleFactor: 1 });
  const cards = Array.from({ length: count }, (_, i) => {
    const name = `slide-${String(i + 1).padStart(2, '0')}.png`;
    return `<figure><img src="file://${path.join(outputDir, name)}"><figcaption>${i + 1}</figcaption></figure>`;
  }).join('');
  await contact.setContent(`
    <style>
      *{box-sizing:border-box} body{margin:0;padding:28px;background:#071b33;font-family:Arial;color:white}
      main{display:grid;grid-template-columns:repeat(3,1fr);gap:22px}
      figure{margin:0;position:relative;border:1px solid #42617f;background:#fff;box-shadow:0 10px 24px #0005}
      img{display:block;width:100%;height:auto}
      figcaption{position:absolute;right:8px;bottom:6px;background:#071b33dd;padding:4px 8px;border-radius:12px;font-weight:700}
    </style><main>${cards}</main>
  `);
  await contact.waitForTimeout(300);
  await contact.screenshot({ path: path.join(outputDir, 'contact-sheet.png'), fullPage: true });
  await browser.close();
  console.log(`Rendered ${count} slides to ${outputDir}`);
})();
