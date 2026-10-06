window.va = window.va || function (...args) {
  (window.vaq = window.vaq || []).push(args);
};

const analyticsScript = document.createElement("script");
analyticsScript.defer = true;
analyticsScript.src = "/_vercel/insights/script.js";
analyticsScript.dataset.sdkn = "@vercel/analytics";
analyticsScript.dataset.sdkv = "2.0.1";
document.head.append(analyticsScript);

window.si = window.si || function (...args) {
  (window.siq = window.siq || []).push(args);
};

const speedInsightsScript = document.createElement("script");
speedInsightsScript.defer = true;
speedInsightsScript.src = "/_vercel/speed-insights/script.js";
speedInsightsScript.dataset.sdkn = "@vercel/speed-insights";
speedInsightsScript.dataset.sdkv = "2.0.0";
document.head.append(speedInsightsScript);
