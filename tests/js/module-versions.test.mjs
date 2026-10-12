// 同一个前端模块在不同文件里必须用同一个缓存版本号导入，否则浏览器会加载两份、各自的状态（如学校码表）互不相通。
import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync,readdirSync} from 'node:fs';

test('every frontend module is imported with a single version tag',()=>{
  const dir=new URL('../../frontend/',import.meta.url);
  const seen={};
  for(const name of readdirSync(dir).filter(n=>n.endsWith('.js'))){
    const text=readFileSync(new URL(name,dir),'utf8');
    for(const m of text.matchAll(/from\s*['"]\.\/([\w.-]+\.js)(\?v=[^'"]*)?['"]/g)){
      (seen[m[1]]??=new Set()).add(m[2]||'');
    }
  }
  const mixed=Object.entries(seen).filter(([,v])=>v.size>1).map(([k,v])=>k+': '+[...v].join(' / '));
  assert.deepEqual(mixed,[]);
});
