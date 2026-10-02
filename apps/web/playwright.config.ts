import { defineConfig } from '@playwright/test';
export default defineConfig({testDir:'e2e',timeout:120000,workers:1,use:{baseURL:'http://localhost:8080',headless:true,viewport:{width:1440,height:1000},trace:'retain-on-failure'},reporter:[['list'],['html',{open:'never'}]]});
