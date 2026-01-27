/**
 * Stealth 注入辅助脚本
 * 
 * 这个脚本是 stealth.min.js 的软链接引用
 * 实际使用时需要读取原始文件内容注入
 * 
 * 原始文件位置:
 * /Users/xuemeizhao/Downloads/add-caption/social_uploader/utils/stealth.min.js
 * 
 * 使用方法 (Clawdbot):
 * 
 * 1. 先读取 stealth.min.js 文件内容
 *    exec: cat /Users/xuemeizhao/Downloads/add-caption/social_uploader/utils/stealth.min.js
 * 
 * 2. 通过 browser evaluate 注入
 *    browser.act(action="act", request={kind: "evaluate", fn: stealth_content})
 * 
 * 或者使用下面的精简版本，只包含最关键的反检测代码:
 */

// 精简版 stealth (核心功能)
(function() {
  // 1. 隐藏 webdriver 标记
  Object.defineProperty(navigator, 'webdriver', {
    get: () => undefined
  });

  // 2. 模拟 Chrome runtime
  window.chrome = {
    runtime: {},
    loadTimes: function() {},
    csi: function() {},
    app: {
      isInstalled: false,
      InstallState: {
        DISABLED: 'disabled',
        INSTALLED: 'installed',
        NOT_INSTALLED: 'not_installed'
      },
      RunningState: {
        CANNOT_RUN: 'cannot_run',
        READY_TO_RUN: 'ready_to_run',
        RUNNING: 'running'
      }
    }
  };

  // 3. 伪装 navigator 属性
  Object.defineProperty(navigator, 'plugins', {
    get: () => [1, 2, 3, 4, 5]
  });

  Object.defineProperty(navigator, 'languages', {
    get: () => ['zh-CN', 'zh', 'en']
  });

  // 4. 隐藏自动化痕迹
  const originalQuery = window.navigator.permissions.query;
  window.navigator.permissions.query = (parameters) => (
    parameters.name === 'notifications' ?
      Promise.resolve({ state: Notification.permission }) :
      originalQuery(parameters)
  );

  // 5. 修复 toString 检测
  const origToString = Function.prototype.toString;
  Function.prototype.toString = function() {
    if (this === window.navigator.permissions.query) {
      return 'function query() { [native code] }';
    }
    return origToString.call(this);
  };

  console.log('[Stealth] Anti-detection measures applied');
})();
