// Editable, compact report figure. Requires the Codex bundled @oai/artifact-tool.
// The same native slide objects produce the PPTX and the report's 3x PNG.
import fs from 'node:fs/promises';
import path from 'node:path';
import { pathToFileURL, fileURLToPath } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const modules = process.env.RUNTIME_NODE_MODULES;
const skill = process.env.PRESENTATIONS_SKILL_DIR;
const python = process.env.RUNTIME_PYTHON;
if (![modules, skill, python].every(p => p && path.isAbsolute(p))) {
  throw new Error('Set absolute RUNTIME_NODE_MODULES, PRESENTATIONS_SKILL_DIR and RUNTIME_PYTHON');
}
const { Presentation, PresentationFile, FileBlob } = await import(pathToFileURL(path.join(modules, '@oai/artifact-tool/dist/artifact_tool.mjs')));
const { resolvePresentationFont, finalizePresentation } = await import(pathToFileURL(path.join(skill, 'container_tools/artifact_tool_utils.mjs')));
const font = resolvePresentationFont({ fontFamily: 'Arial' });
const build = path.join(root, 'tmp/workflow-v4');
const output = path.join(root, 'output/figures');
await fs.mkdir(build, {recursive:true});
await fs.mkdir(output, {recursive:true});
await fs.mkdir(path.join(root, 'report/figures/v4'), {recursive:true});
const W = 1280, H = 414;
const presentation = Presentation.create({slideSize:{width:W, height:H}});
const slide = presentation.slides.add();
slide.background.fill = '#FFFFFF';
const C = {ink:'#233244', gray:'#596777', rule:'#AFBAC6', teal:'#007F8B', purple:'#8051A5',
  green:'#267854', amber:'#A86A1D', blue:'#3778AC'};
let serial = 0;
function shape(geometry,x,y,w,h,fill='none',stroke='none',width=1.5) {
  return slide.shapes.add({geometry,name:`figure-object-${serial++}`,position:{left:x,top:y,width:w,height:h},
    fill,line:{fill:stroke,width}});
}
function text(content,x,y,w,h,size=23,color=C.ink,bold=false) {
  const item=shape('textbox',x,y,w,h);
  item.text=content;
  item.text.style={typeface:font,fontSize:size,color,bold,autoFit:'none',verticalAlignment:'middle'};
  return item;
}
function line(points,color=C.gray,width=2.1,dashed=false) {
  const xs=points.map(p=>p[0]),ys=points.map(p=>p[1]);
  const x=Math.min(...xs),y=Math.min(...ys),w=Math.max(...xs)-x||.01,h=Math.max(...ys)-y||.01;
  return slide.shapes.add({geometry:'custom',name:`path-${serial++}`,position:{left:x,top:y,width:w,height:h},fill:'none',
    line:{fill:color,width,style:dashed?'dashed':'solid'},customPaths:[{width:w,height:h,
      commands:points.map((p,i)=>({[i?'lineTo':'moveTo']:{x:p[0]-x,y:p[1]-y}}))}]});
}
function arrow(points,color=C.gray,dashed=false) {
  line(points,color,2.2,dashed);
  const [x,y]=points.at(-1), [a,b]=points.at(-2);
  const dx=Math.sign(x-a),dy=Math.sign(y-b);
  const pts=dx?[[x-8*dx,y-4],[x,y],[x-8*dx,y+4]]:[[x-4,y-8*dy],[x,y],[x+4,y-8*dy]];
  line(pts,color,2.2);
}
function icon(kind,x,y,s,color) {
  const L=(p)=>line(p.map(([a,b])=>[x+a*s/24,y+b*s/24]),color,2.1);
  const R=(a,b,w,h,g='rect')=>shape(g,x+a*s/24,y+b*s/24,w*s/24,h*s/24,'none',color,2.1);
  if(kind==='file') { L([[5,2],[15,2],[20,7],[20,22],[5,22],[5,2]]);L([[15,2],[15,7],[20,7]]);L([[10,11],[7,14],[10,17]]);L([[15,11],[18,14],[15,17]]); }
  if(kind==='branches') { L([[5,3],[5,19],[19,19]]);L([[5,10],[17,10],[17,3]]);R(2,0,6,6,'ellipse');R(14,0,6,6,'ellipse');R(16,16,6,6,'ellipse'); }
  if(kind==='chip') { R(5,5,14,14);R(9,9,6,6);for(const p of [8,16]) {L([[p,1],[p,5]]);L([[p,19],[p,23]]);L([[1,p],[5,p]]);L([[19,p],[23,p]]);} }
  if(kind==='chat') { L([[3,3],[21,3],[21,17],[12,17],[6,22],[6,17],[3,17],[3,3]]);for(const p of [7,12,17])R(p-1,9,2,2,'ellipse'); }
  if(kind==='queue') { for(const q of [2,9,16]){R(2,q,17,5);L([[21,q+1],[23,q+2.5],[21,q+4]]);} }
  if(kind==='shield') { L([[12,2],[21,5],[20,15],[16,20],[12,23],[8,20],[4,15],[3,5],[12,2]]);L([[7,12],[10,15],[17,8]]); }
  if(kind==='bug') { R(7,6,10,14,'ellipse');R(9,3,6,5,'ellipse');L([[9,3],[7,0]]);L([[15,3],[17,0]]);for(const q of [9,14,18]){L([[3,q],[7,q]]);L([[17,q],[21,q]]);} }
  if(kind==='check') {R(1,1,22,22,'ellipse');L([[5,12],[10,17],[19,7]]);}
  if(kind==='question') {R(1,1,22,22,'ellipse');L([[8,8],[9,5],[15,5],[17,8],[16,11],[12,13],[12,16]]);R(11.5,19,1,1,'ellipse');}
  if(kind==='clock') {R(2,2,20,20,'ellipse');L([[12,5],[12,12],[17,15]]);}
  if(kind==='feedback') {L([[20,8],[17,3],[8,3],[3,8],[3,16],[8,21],[17,21],[21,17]]);L([[20,2],[20,8],[14,8]]);}
}

// Each top item is an alternative policy; arrows only affect queue order.
text('Priority policy',20,19,265,32,24,C.ink,true);
text('Varies by arm / phase',20,53,275,32,21,C.gray);
icon('branches',337,21,40,C.gray);
text('Local orders',392,15,180,35,24,C.gray,true);
text('DFS / Portfolio',392,50,180,33,21,C.gray);
icon('chip',617,21,40,C.teal);
text('SMT lookahead',671,15,245,35,24,C.teal,true);
text('Charged advice cost',671,50,250,33,21,C.gray);
icon('chat',949,21,40,C.purple);
text('LLM preferences',1003,15,265,35,24,C.purple,true);
text('Verdicts unverified',1003,50,265,33,21,C.gray);
line([[457,94],[457,123],[1106,123],[1106,94]],C.rule,2,true);
line([[785,94],[785,123]],C.rule,2,true);
arrow([[490,123],[490,192]],C.gray,true);
text('Ordering only; alternatives remain queued',537,132,657,35,22,C.gray);

// Accepted evidence follows this source-derived execution path.
shape('rect',18,196,244,117,'#F4F6F8',C.rule,1.2);
icon('file',35,228,43,C.gray);
text('Source + AST',92,206,169,45,22,C.ink,true);
text('Site IDs +\nbranch catalog',92,250,168,45,19,C.gray);
shape('rect',357,196,267,117,'#F4F6F8',C.rule,1.2);
icon('queue',375,228,43,C.gray);
text('Retained\nfrontier',432,201,190,58,22,C.ink,true);
text('Execute / rank',432,267,188,35,20,C.gray);
shape('rect',719,196,267,117,'#EDF7F7',C.teal,1.2);
icon('shield',738,228,43,C.teal);
text('Source\nverification',793,201,192,58,22,C.ink,true);
text('Z3: path + d = 0',793,267,188,35,20,C.gray);
arrow([[269,254],[346,254]],C.gray);
arrow([[631,254],[708,254]],C.gray);
arrow([[993,254],[1037,254]],C.gray);
line([[1043,205],[1043,298]],C.rule,1.5);
icon('bug',1060,181,31,C.amber);text('Confirmed\nwitness',1103,169,176,54,21,C.ink,true);
icon('check',1060,236,31,C.green);text('Complete refutation',1103,232,176,41,21,C.ink,true);
icon('question',1060,291,31,C.gray);text('Unknown',1103,287,176,37,24,C.ink,true);
for(const y of [205,254,298]) line([[1043,y],[1053,y]],C.rule,1.5);

// Compact annotated variants, kept outside the core acceptance path.
line([[18,340],[1262,340]],'#D8DEE5',1.1);
icon('feedback',22,359,31,C.purple);
text('Feedback: a verification failure can revise priorities; frontier and counters persist',67,350,1195,43,22,C.ink);
icon('clock',22,396-9,25,C.blue);
text('Live trials: 30 s includes startup, model waiting and verification; request gates are method-specific',67,380,1195,33,21,C.gray);
slide.speakerNotes.textFrame.setText(
  'Source: report/v4.tex sections 3 and 5; src/symdiv/search.py; src/symdiv/experiment_v4.py. '+
  'Priority policies vary by arm and phase; local-first and fallback schedules can switch policies. Model verdicts never accept findings. '+
  'Complete refutation requires exhaustive supported exploration. Actual source failures may trigger one repair in the resource-feedback arm; corrections are disabled in live timing. '+
  'Selective gates and the separately frozen SMT-first extension are described in the report. Icons are native editable diagram objects.');

const candidate = path.join(build,'workflow-candidate.pptx');
await (await PresentationFile.exportPptx(presentation)).save(candidate);
const finalPath = process.env.WORKFLOW_OUTPUT || path.join(output,'symdiv-workflow-v4.pptx');
await finalizePresentation({workspaceDir:root,candidatePath:candidate,finalPath,pythonExecutable:python,
  integrityValidatorPath:path.join(skill,'container_tools/inspect_presentation_package_integrity.py'),
  layoutValidatorPath:path.join(skill,'container_tools/inspect_presentation_layout_geometry.py'),
  explicitTotalSlideCount:1, requiredNativeTableOwnerSlides:[],requiredNativeChartOwnerSlides:[],
  layoutArgs:['--expected-slide-size-emu',`${W*9525},${H*9525}`,'--validate-heading-fit'],
  fontPolicy:{basis:'design',families:[font]},verifyArtifactToolImport:true,
  receiptPath:path.join(build, path.basename(finalPath)+'.validation.json')});
const finalPresentation = await PresentationFile.importPptx(await FileBlob.load(finalPath));
const finalSlide = finalPresentation.slides.items[0];
const preview=await finalPresentation.export({slide:finalSlide,format:'png',scale:3});
await fs.writeFile(path.join(root,'report/figures/v4/workflow.png'),new Uint8Array(await preview.arrayBuffer()));
const small=await finalPresentation.export({slide:finalSlide,format:'png',scale:1});
await fs.writeFile(path.join(build,'workflow-preview.png'),new Uint8Array(await small.arrayBuffer()));
const layout=await slide.export({format:'layout'});
await fs.writeFile(path.join(build,'workflow-layout.json'),await layout.text());
console.log('Saved editable workflow and report PNG:',finalPath);
