const { chromium } = require('playwright');

async function checkViewport(browser, name, viewport) {
  const page = await browser.newPage({ viewport });
  await page.addInitScript(() => localStorage.setItem('anima_factory_auto-shutdown', 'true'));
  const errors = [];
  page.on('console', message => {
    if (message.type() === 'error') errors.push(message.text());
  });
  page.on('pageerror', error => errors.push(error.message));

  await page.goto('http://host.docker.internal:8000', { waitUntil: 'networkidle' });
  if (await page.locator('#auto-shutdown').isChecked()) throw new Error(name + ': shutdown remained enabled');
  await page.locator('button', { hasText: 'Browse' }).first().click();
  const modal = page.locator('#docker-file-browser');
  await modal.waitFor({ state: 'visible' });

  const modalBox = await modal.locator('.docker-browser').boundingBox();
  console.log(name, viewport, modalBox);
  if (!modalBox || modalBox.x < 0 || modalBox.y < 0 ||
      modalBox.x + modalBox.width > viewport.width || modalBox.y + modalBox.height > viewport.height) {
    throw new Error(`${name}: file browser extends outside the viewport`);
  }
  const overflow = await page.evaluate(() => ({
    width: document.documentElement.scrollWidth > document.documentElement.clientWidth,
    modal: document.querySelector('.docker-browser-list').scrollWidth >
      document.querySelector('.docker-browser-list').clientWidth,
  }));
  if (overflow.width || overflow.modal) throw new Error(`${name}: horizontal overflow detected`);
  if (errors.length) throw new Error(`${name}: browser errors: ${errors.join('; ')}`);

  await page.screenshot({ path: `/results/${name}.png`, fullPage: true });
  await page.close();
}

(async () => {
  const browser = await chromium.launch({ headless: true });
  try {
    await checkViewport(browser, 'desktop', { width: 1440, height: 900 });
    await checkViewport(browser, 'mobile', { width: 390, height: 844 });
  } finally {
    await browser.close();
  }
})();
