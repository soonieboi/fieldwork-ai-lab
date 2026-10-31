const {defineConfig}=require('@playwright/test');
module.exports=defineConfig({
  testDir:'./tests/browser',fullyParallel:false,workers:1,retries:0,
  timeout:20000,expect:{timeout:5000},reporter:'list',
  use:{baseURL:'http://127.0.0.1:8765',browserName:'chromium',headless:true,
    launchOptions:{args:['--no-proxy-server']},trace:'off',screenshot:'off'},
  webServer:{command:'python3 -m lab serve --port 8765',url:'http://127.0.0.1:8765',reuseExistingServer:false,timeout:10000,
    env:{LAB_AGENT_ENABLED:'0',LAB_GENERATION_ENABLED:'0',LAB_SERVING_ENABLED:'0'}},
});
