const pptxgen = require('pptxgenjs');
const path = require('path');
const fs = require('fs');

(async () => {
  const root = __dirname;
  const imageDir = path.join(root, 'rendered');
  const images = fs.readdirSync(imageDir)
    .filter(name => /^slide-\d+\.png$/.test(name))
    .sort();

  if (!images.length) throw new Error('No rendered slide images found.');

  const pptx = new pptxgen();
  pptx.layout = 'LAYOUT_WIDE';
  pptx.author = 'Codex';
  pptx.subject = 'LTC Skill 落地与技术评估';
  pptx.title = 'LTC Skill 落地评估';
  pptx.company = 'LTC';
  pptx.lang = 'zh-CN';
  pptx.theme = {
    headFontFace: 'Microsoft YaHei',
    bodyFontFace: 'Microsoft YaHei',
    lang: 'zh-CN'
  };

  for (const image of images) {
    const slide = pptx.addSlide();
    slide.background = { color: '071B33' };
    slide.addImage({ path: path.join(imageDir, image), x: 0, y: 0, w: 13.333, h: 7.5 });
  }

  const output = path.join(root, 'LTC_Skill落地评估.pptx');
  await pptx.writeFile({ fileName: output });
  console.log(`Wrote ${output}`);
})();
