browser.runtime.onMessage.addListener((message) => {
  if (message?.type !== 'CAPTURE_VISIBLE_TAB') return undefined;

  return browser.tabs.captureVisibleTab(undefined, {
    format: 'jpeg',
    quality: 85,
  });
});
