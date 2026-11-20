/* Runs before everything else in a page: a fixed clock and a seeded Math.random, so libraries that take ids or
 * jitter from them when they load (Iconify's id prefix, roughjs) give the same output every time. driver.js
 * resets both before each render. */
(function () {
  "use strict";
  let a = 0x6d65726d;
  Math.random = function () {
    a = (a + 0x6D2B79F5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
  Date.now = () => 1767225600000;
})();
