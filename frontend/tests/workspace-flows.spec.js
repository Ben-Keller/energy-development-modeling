const {test, expect} = require('@playwright/test');
const AxeBuilder = require('@axe-core/playwright').default;
const {PROJECT, DRAFT_RUN, DATASET, mockPlatformApi, publicRun, completedComparisonRun, comparisonSummary, openProjects} = require('./platform-fixtures');

async function completed(page, options={}) {
  const run = completedComparisonRun('run_visual',1,'Current policy','baseline',2030);
  const summary = comparisonSummary(run,1);
  await mockPlatformApi(page,{projectRuns:[run],summaries:{[run.run_id]:summary},...options});
  return {run,summary};
}

test('setup fields, brand and dialogs fit all target widths and save the frozen contract', async ({page}, info) => {
  await mockPlatformApi(page);
  const errors=[]; page.on('pageerror',error=>errors.push(error.message));
  await openProjects(page);
  await page.getByRole('button',{name:'Open project',exact:true}).click();
  await page.getByRole('button',{name:'Open model',exact:true}).click();
  for (const width of [360,412,768,1280,1440]) {
    await page.setViewportSize({width,height:960});
    await page.evaluate(()=>document.fonts.ready);
    const bounds = await page.locator('.setup-form-panel').evaluate(el => {
      const nodes=[document.querySelector('.edim-brand'),...el.querySelectorAll('select,input:not([type=hidden])')];
      return nodes.map(node=>{const r=node.getBoundingClientRect(); return {left:r.left,right:r.right,width:r.width,viewport:innerWidth};});
    });
    for (const box of bounds) { expect(box.left,JSON.stringify(box)).toBeGreaterThanOrEqual(0); expect(box.right,JSON.stringify(box)).toBeLessThanOrEqual(width); expect(box.width).toBeGreaterThan(0); }
    await page.screenshot({path:info.outputPath(`setup-${width}-${info.project.name}.png`),fullPage:true});
  }
  const saved=page.waitForRequest(r=>r.method()==='PATCH' && r.url().includes('/runs/'));
  await page.getByLabel('Carbon price (USD/tCO2) value',{exact:true}).fill('80');
  await page.getByRole('button',{name:'Save draft',exact:true}).click();
  const payload=(await saved).postDataJSON();
  expect(Object.keys(payload.request).sort()).toEqual(['energy_model_engine','levers','model_architecture_id','run_name','run_profile','scenario']);
  expect(payload.request.levers.carbon_price_usd_per_tco2).toBe(80);
  await expect(page.getByText('Draft saved.',{exact:true})).toBeVisible();
  expect(errors).toEqual([]);
});

test('model routes survive reload, back and forward; missing links recover',async({page})=>{
  const {run}=await completed(page);
  await page.goto(`/#/projects/${PROJECT.project_id}/models/${run.run_id}/system`);
  await expect(page.getByRole('tab',{name:'Energy system',exact:true})).toHaveAttribute('aria-selected','true');
  await page.getByRole('tab',{name:'Method',exact:true}).click();
  await expect(page).toHaveURL(/\/method$/);
  await page.goBack();
  await expect(page.getByRole('tab',{name:'Energy system',exact:true})).toHaveAttribute('aria-selected','true');
  await page.goForward();
  await expect(page.getByRole('tab',{name:'Method',exact:true})).toHaveAttribute('aria-selected','true');
  await page.reload();
  await expect(page.getByRole('tab',{name:'Method',exact:true})).toHaveAttribute('aria-selected','true');
  await page.getByRole('button',{name:/User menu for/}).click();
  await page.getByRole('button',{name:'Dataset library',exact:true}).click();
  await page.reload();
  await expect(page.getByRole('heading',{name:'Dataset library'})).toBeVisible();
  await page.goto('/#/projects/missing');
  await expect(page.getByRole('alert')).toContainText('project is unavailable');
  await expect(page.getByRole('heading',{name:'Your Projects',exact:true})).toBeVisible();
});

test('model actions support rename, duplicate, cancel deletion and protected active models',async({page})=>{
  await mockPlatformApi(page);
  let deleted=0;
  await page.route('**/api/projects/*/runs/*',async route=>{
    const req=route.request();
    if(req.url().endsWith('/duplicate')) {return route.fulfill({json:{run:publicRun({...DRAFT_RUN,run_id:'duplicate_1',run_name:'Copy'})}});}
    if(req.method()==='DELETE'){deleted++; return route.fulfill({json:{ok:true}});}
    return route.fallback();
  });
  await openProjects(page);
  await page.getByRole('button',{name:'Open project',exact:true}).click();
  await page.getByRole('button',{name:'Model actions',exact:true}).click();
  let modal=page.getByRole('dialog',{name:'Model actions'});
  await modal.getByLabel('Model name',{exact:true}).fill('Renamed model');
  await modal.getByRole('button',{name:'Save name',exact:true}).click();
  await expect(page.getByRole('heading',{name:'Renamed model',exact:true})).toBeVisible();
  await page.getByRole('button',{name:'Model actions',exact:true}).click();
  page.once('dialog',dialog=>dialog.dismiss());
  await modal.getByRole('button',{name:'Delete model',exact:true}).click();
  await expect(modal).toBeVisible(); expect(deleted).toBe(0);
  await modal.getByRole('button',{name:'Duplicate model',exact:true}).click();
  await expect(page.locator('.setup-form-panel')).toBeVisible();
  await page.unroute('**/api/**');
  await mockPlatformApi(page,{projectRuns:[{...DRAFT_RUN,status:'running'}]});
  await page.route('**/api/executions/*/status',route=>route.fulfill({json:publicRun({...DRAFT_RUN,status:'running'})}));
  await openProjects(page); await page.getByRole('button',{name:'Open project',exact:true}).click();
  await page.getByRole('button',{name:'Model actions',exact:true}).click();
  await expect(modal.getByRole('button',{name:'Delete model',exact:true})).toBeDisabled();
});

test('recorded inputs load lazily, preserve recorded versions and expose evidence',async({page},info)=>{
  const {run}=await completed(page);
  let reads=0;
  await page.route('**/diagnostics',async route=>{reads++; await route.fulfill({json:{run:{dataset_snapshot:{datasets:[{id:'demand',label:'National demand',version_id:'historic-1',filename:'original.csv'}]}}}});});
  await page.goto(`/#/projects/${PROJECT.project_id}/models/${run.run_id}/overview`);
  await expect(page.locator('.evidence-notice')).toBeVisible(); expect(reads).toBe(0);
  await page.locator('.recorded-inputs > summary').click();
  await expect(page.locator('.recorded-inputs')).toContainText('historic-1');
  await expect(page.locator('.recorded-inputs')).not.toContainText(DATASET.active_version_id);
  await page.screenshot({path:info.outputPath(`results-${info.project.name}.png`),fullPage:true});
  await page.locator('.recorded-inputs > summary').click();
  await page.unroute('**/diagnostics');
  await page.route('**/diagnostics',route=>route.fulfill({status:404,json:{detail:'Unavailable'}}));
  await page.locator('.recorded-inputs > summary').click();
  await expect(page.locator('.recorded-inputs')).toContainText('provenance is unavailable');
  await expect(page.getByRole('tab',{name:'Overview',exact:true})).toBeVisible();
});

test('empty and filtered charts are safe and filtering stays local',async({page})=>{
  const run=completedComparisonRun('empty_test',1,'Chart test','baseline',2030);
  const summary=comparisonSummary(run,1);
  summary.generation_by_tech.records=[];
  const errors=[];page.on('pageerror',error=>errors.push(error.message));
  await mockPlatformApi(page,{projectRuns:[run],summaries:{[run.run_id]:summary}});
  await page.goto(`/#/projects/${PROJECT.project_id}/models/${run.run_id}/system`);
  await expect(page.getByRole('tab',{name:'Energy system',exact:true})).toHaveAttribute('aria-selected','true');
  const charts=page.locator('.ranked-bars');
  await charts.first().getByRole('searchbox').fill('no such label');
  await expect(charts.first()).toContainText('No matching records.');
  await expect(charts.nth(1).getByRole('searchbox')).toHaveValue('');
  expect(errors).toEqual([]);
});

test('library sorting, assignment and protected deletion use existing operations',async({page},info)=>{
  await mockPlatformApi(page);
  let assignment;
  await page.route('**/api/projects/*/datasets',async route=>{assignment=route.request().postDataJSON(); await route.fulfill({json:{ok:true}});});
  await page.route('**/api/input-datasets/*/versions/*',async route=>{
    if(route.request().method()==='DELETE') return route.fulfill({status:409,json:{detail:'This version is referenced by a submitted model.'}});
    return route.fallback();
  });
  await page.goto('/#/datasets');
  await expect(page.getByRole('heading',{name:'Dataset library'})).toBeVisible();
  await expect(page.locator('.dataset-table')).toContainText('128');
  await page.getByLabel('Sort datasets',{exact:true}).selectOption('size');
  await expect(page.locator('.dataset-table th').filter({hasText:'Size'})).toHaveAttribute('aria-sort','ascending');
  await page.getByRole('button',{name:'Add to project',exact:true}).click();
  await page.getByRole('dialog').getByRole('button',{name:'Add to project',exact:true}).click();
  await expect(page.getByRole('dialog')).toHaveCount(0);
  expect(assignment).toEqual({dataset_id:DATASET.id,version_id:'version_01'});
  await page.locator('.dataset-overflow-menu summary').click();
  page.once('dialog',d=>d.accept());
  await page.getByRole('button',{name:'Delete version',exact:true}).click();
  await expect(page.getByRole('status').filter({hasText:'referenced'})).toBeVisible();
  await expect(page.locator('.dataset-table')).toContainText('demand.csv');
  await page.screenshot({path:info.outputPath(`datasets-${info.project.name}.png`),fullPage:true});
  const a11y=await new AxeBuilder({page}).include('.dataset-management-view').analyze();
  expect(a11y.violations).toEqual([]);
});

test('all returned reports and exports remain reachable',async({page})=>{
  const reports=Array.from({length:9},(_,i)=>({report_id:`report_${i}`,title:`Report ${i}`,created_at:'2026-09-20T10:00:00Z',download_url:'/report'}));
  const exports=Array.from({length:9},(_,i)=>({export_id:`export_${i}`,created_at:'2026-09-20T10:00:00Z',download_url:'/export'}));
  await mockPlatformApi(page,{reports,exports});
  await page.goto(`/#/projects/${PROJECT.project_id}`);
  await page.locator('.project-secondary-disclosure summary').filter({hasText:'Reports'}).click();
  await page.locator('.project-secondary-disclosure summary').filter({hasText:'Exports'}).click();
  await expect(page.locator('.project-artifact-list').first().locator('.diagram-dataset-version-row')).toHaveCount(9);
  await expect(page.locator('.project-artifact-list').nth(1).locator('.diagram-dataset-version-row')).toHaveCount(9);
});

test('library create, version upload, rename and deletion refresh persisted metadata',async({page})=>{
  await mockPlatformApi(page);
  let dataset=null, versions=[]; let creates=0;
  await page.route('**/api/input-datasets**',async route=>{
    const req=route.request(), url=new URL(req.url());
    if(url.pathname==='/api/input-datasets') {
      if(req.method()==='POST'){creates++;dataset={...DATASET,...req.postDataJSON(),id:'custom_data',active_version_id:'',project_ids:[]};return route.fulfill({json:{dataset}});}
      return route.fulfill({json:{datasets:dataset?[dataset]:[]}});
    }
    if(url.pathname==='/api/input-datasets/custom_data' && req.method()==='PATCH') {dataset={...dataset,...req.postDataJSON()};return route.fulfill({json:{dataset}});}
    if(url.pathname.endsWith('/upload')) {const version={version_id:`v${versions.length+1}`,filename:'costs.csv',size_bytes:36,created_at:'2026-09-20T10:00:00Z',project_ids:[]};versions.push(version);dataset.active_version_id=version.version_id;return route.fulfill({json:{ok:true,version}});}
    if(url.pathname.endsWith('/versions')) return route.fulfill({json:{versions}});
    if(req.method()==='DELETE') {versions=versions.filter(row=>!url.pathname.endsWith(row.version_id));return route.fulfill({json:{ok:true}});}
    return route.fallback();
  });
  await page.goto('/#/datasets');
  await page.getByRole('button',{name:'Add dataset',exact:true}).click();
  const modal=page.getByRole('dialog',{name:'Add dataset'});
  await modal.getByLabel('Dataset name',{exact:true}).fill('Technology costs');
  await modal.getByLabel('File',{exact:true}).setInputFiles({name:'costs.csv',mimeType:'text/csv',buffer:Buffer.from('technology,cost\nsolar,100\n')});
  await modal.getByRole('button',{name:'Create dataset',exact:true}).click();
  await expect(page.locator('.dataset-table tbody tr')).toHaveCount(1);expect(creates).toBe(1);
  await page.locator('.dataset-overflow-menu summary').click();
  await page.getByRole('button',{name:'Rename',exact:true}).click();
  await page.getByRole('dialog').getByLabel('Dataset name',{exact:true}).fill('Updated costs');
  await page.getByRole('button',{name:'Save name',exact:true}).click();
  await expect(page.locator('.dataset-table')).toContainText('Updated costs');
  await page.locator('.dataset-overflow-menu summary').click();
  await page.getByRole('button',{name:'Upload version',exact:true}).click();
  await page.getByRole('dialog').getByLabel('File',{exact:true}).setInputFiles({name:'costs.csv',mimeType:'text/csv',buffer:Buffer.from('technology,cost\nsolar,90\n')});
  await page.getByRole('dialog').getByRole('button',{name:'Upload version',exact:true}).click();
  await expect(page.locator('.dataset-table tbody tr')).toHaveCount(2);
  await page.locator('.dataset-overflow-menu summary').first().click();
  page.once('dialog',dialog=>dialog.accept());
  await page.getByRole('button',{name:'Delete version',exact:true}).first().click();
  await expect(page.locator('.dataset-table tbody tr')).toHaveCount(1);
});

test('responsive dialogs retain gutters, keyboard focus and return to their trigger',async({page})=>{
  await mockPlatformApi(page); await openProjects(page);
  for(const width of [360,412,768,1280,1440]) {
    await page.setViewportSize({width,height:900});
    const trigger=page.getByRole('button',{name:'New project',exact:true});
    await trigger.click();
    const modal=page.getByRole('dialog',{name:'Create project'});
    await expect(modal).toBeVisible();
    const rect=await modal.boundingBox();expect(rect.x).toBeGreaterThanOrEqual(10);expect(rect.x+rect.width).toBeLessThanOrEqual(width-10);
    await page.keyboard.press('Tab');expect(await modal.evaluate(el=>el.contains(document.activeElement))).toBe(true);
    await page.keyboard.press('Escape');await expect(modal).toBeHidden();await expect(trigger).toBeFocused();
  }
});

test('recent activity uses timestamps and opens the correct model and report', async ({page}, info) => {
  const older = {...DRAFT_RUN, run_id:'older', updated_at:'2026-09-01T00:00:00Z', created_at:'2026-09-01T00:00:00Z'};
  const newer = {...DRAFT_RUN, run_id:'newer', updated_at:'2026-09-20T00:00:00Z', created_at:'2026-09-01T00:00:00Z'};
  const reports = [{report_id:'old',project_id:PROJECT.project_id,status:'ready',created_at:'2026-09-01T00:00:00Z'}, {report_id:'new',project_id:PROJECT.project_id,status:'ready',created_at:'2026-09-20T00:00:00Z'}];
  await mockPlatformApi(page,{projectRuns:[older,newer],reports});
  await page.goto(`/#/projects/${PROJECT.project_id}`);
  const recent = page.getByRole('region',{name:'Recent project activity'});
  const models = await page.getByRole('region',{name:'Project models',exact:true}).boundingBox();
  const sidebar = page.getByRole('complementary',{name:'Project activity and files'});
  const side = await sidebar.boundingBox();
  const heading = await page.locator('.project-information-heading-row').boundingBox();
  expect(Math.abs(models.x - heading.x)).toBeLessThanOrEqual(1);
  expect(models.x).toBeGreaterThanOrEqual(16);
  expect(Math.abs(page.viewportSize().width - side.x - side.width - models.x)).toBeLessThanOrEqual(2);
  if (page.viewportSize().width > 1000) {
    expect(side.x).toBeGreaterThanOrEqual(models.x + models.width);
    expect(Math.abs(side.y-models.y)).toBeLessThanOrEqual(2);
  } else {
    expect(side.y).toBeGreaterThanOrEqual(models.y + models.height);
  }
  await expect(sidebar.locator('.project-secondary-disclosure')).toHaveCount(2);
  await page.locator('.project-content-layout').screenshot({path:info.outputPath(`project-sidebar-${info.project.name}.png`)});
  await expect(recent.getByRole('link',{name:'Download latest report'})).toHaveAttribute('href',/reports\/new\//);
  await recent.screenshot({path:info.outputPath(`recent-activity-${info.project.name}.png`)});
  await recent.getByRole('button',{name:/Open latest model:/}).click();
  await expect(page).toHaveURL(/\/models\/newer\/setup$/);
});

test('evidence stays collapsed until requested and preserves missing bounds',async({page},info)=>{
  const run=completedComparisonRun('evidence_summary',1,'Evidence check','baseline',2030);
  const summary=comparisonSummary(run,1);
  summary.integrated_results.development_uncertainty={method:'relative_bounds_v1',totals_bounds:{jobs_total_low:0,jobs_total_high:20,gva_total_musd_low:5}};
  await mockPlatformApi(page,{projectRuns:[run],summaries:{[run.run_id]:summary}});
  await page.goto(`/#/projects/${PROJECT.project_id}/models/${run.run_id}/overview`);
  const evidence=page.getByRole('region',{name:'Evidence summary',exact:true});
  await expect(evidence).not.toBeVisible();
  await expect(page.locator('.evidence-notice-body')).not.toBeVisible();
  await page.locator('.evidence-notice > summary').click();
  await expect(page.locator('.evidence-notice-body')).toBeVisible();
  await page.locator('.results-evidence-disclosure > summary').click();
  await expect(evidence).toBeVisible();
  await expect(evidence).toContainText('0 to 20');
  await expect(evidence).toContainText('relative_bounds_v1');
  await expect(evidence).toContainText('Unavailable');
  await evidence.screenshot({path:info.outputPath(`evidence-summary-${info.project.name}.png`)});
  await expect(page.locator('.results-evidence-disclosure')).toHaveAttribute('open','');
  for(const width of [360,1280]) {
    await page.setViewportSize({width,height:960});
    const bounds=await evidence.boundingBox();
    expect(bounds.x).toBeGreaterThanOrEqual(0);expect(bounds.x+bounds.width).toBeLessThanOrEqual(width);
  }
});


test('dataset library opens from the account menu and projects section',async({page})=>{
  await mockPlatformApi(page);
  await page.goto('/');
  await page.getByRole('button',{name:/User menu for/}).click();
  await page.getByRole('button',{name:'Dataset library',exact:true}).click();
  await expect(page).toHaveURL(/#\/datasets$/);
  await expect(page.locator('.header-user-menu')).not.toHaveAttribute('open','');
  await page.getByRole('button',{name:'Back to projects',exact:false}).click();
  await expect(page.getByRole('heading',{name:'Your Projects',level:1})).toBeVisible();
  await expect(page.locator('.workspace-navigation')).toHaveCount(0);
  await page.getByRole('button',{name:'Open dataset library',exact:false}).click();
  await expect(page).toHaveURL(/#\/datasets$/);
  await page.reload();
  await expect(page.getByRole('heading',{name:'Dataset library',exact:true})).toBeVisible();
});

test('one persistent header keeps its dimensions across page navigation',async({page})=>{
  await mockPlatformApi(page);
  await page.goto('/');
  await page.getByRole('button',{name:'Open projects',exact:true}).waitFor();
  await page.evaluate(()=>document.fonts.ready);
  const baseline=await page.locator('.edim-topbar').evaluate(el=>{
    window.__persistentHeader=el;
    const r=el.getBoundingClientRect();return {width:r.width,height:r.height};
  });
  async function checkHeader() {
    await expect(page.locator('.edim-topbar')).toHaveCount(1);
    const actual=await page.locator('.edim-topbar').evaluate(el=>{
      const r=el.getBoundingClientRect();return {same:el===window.__persistentHeader,width:r.width,height:r.height};
    });
    expect(actual).toEqual({same:true,...baseline});
  }
  await page.getByRole('button',{name:'Open projects',exact:true}).click();
  await page.getByRole('heading',{name:'Your Projects',level:1}).waitFor();await checkHeader();
  await page.getByRole('button',{name:'Open project',exact:true}).click();
  await page.getByRole('heading',{name:'Models',exact:true}).waitFor();await checkHeader();
  await page.getByRole('button',{name:'Open model',exact:true}).click();
  await page.locator('.setup-form-panel').waitFor();await checkHeader();
  await page.getByRole('button',{name:/User menu for/}).click();
  await page.getByRole('button',{name:'Dataset library',exact:true}).click();
  await page.getByRole('heading',{name:'Dataset library',exact:true}).waitFor();await checkHeader();
  await page.getByRole('button',{name:'Return to landing page',exact:true}).click();
  await page.getByRole('button',{name:'Explore the methodology',exact:true}).click();
  await page.locator('.methodology-shell').waitFor();await checkHeader();
});
