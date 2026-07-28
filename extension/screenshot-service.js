browser.runtime.onMessage.addListener((message, sender) => {
  if (message?.type !== 'CAPTURE_PAGE_SEGMENT') return undefined;

  const rect = message.rect;
  const rectValues = rect && [rect.x, rect.y, rect.width, rect.height];
  if (!rectValues || rectValues.some((value) => !Number.isFinite(value)) ||
      rect.x < 0 || rect.y < 0 || rect.width <= 0 || rect.height <= 0) {
    return Promise.reject(new Error('Invalid page screenshot rectangle.'));
  }

  if (!sender.tab?.id) {
    return Promise.reject(new Error('Page screenshot request did not originate from a tab.'));
  }

  return browser.tabs.get(sender.tab.id).then((tab) => {
    if (!tab.active) {
      throw new Error('Keep the page tab active until screenshot capture is complete.');
    }

    return browser.tabs.captureVisibleTab(tab.windowId, {
      format: 'jpeg',
      quality: 85,
      rect,
      scale: 1,
    });
  });
});
