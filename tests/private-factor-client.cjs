const assert = require("node:assert/strict");
const { pathToFileURL } = require("node:url");
const path = require("node:path");
(async () => {
  const { validateFile, draftPayload, fileDigest, PrivateFactorClient } =
    await import(pathToFileURL(path.resolve("pages/factor-db-dashboard/submission-client.mjs")));
  assert.throws(() => validateFile({name:"../bad.py",size:5},0));
  assert.throws(() => validateFile({name:"payload.exe",size:5},0));
  assert.throws(() => validateFile({name:"payload.py",size:26*1024*1024},0));
  assert.throws(() => validateFile({name:"payload.py",size:10},100*1024*1024));
  assert.equal(validateFile({name:"valid.py",size:5},0),"text/x-python");
  const input = {factor_id:"test:alpha",version:1,title:"alpha",formula:"Mean(x,40)",
    license:"owned",verification_stage:"partial_proof",code_hash:"a".repeat(64),
    config_hash:"b".repeat(64),data_hash:"c".repeat(64),metrics:{ic:-.04},blockers:["missing"]};
  assert.throws(() => draftPayload({...input,owner_id:"impostor"}));
  assert.throws(() => draftPayload({...input,state:"admitted"}));
  assert.throws(() => draftPayload({...input,data_hash:"bad"}));
  assert.deepEqual(draftPayload(input),input);
  const blob = new Blob(["hello"]);
  assert.equal(await fileDigest(blob),"2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824");
  let calls = 0;
  const transport = { rpc: async () => { calls++; return {data:null,error:{message:"denied"}}; } };
  const client = new PrivateFactorClient(transport);
  assert.throws(() => client.create({...input,owner_id:"bad"}));
  assert.equal(calls,0);
  await assert.rejects(() => client.create(input),/denied/);
  assert.equal(calls,1);
  console.log(JSON.stringify({client_checks:12,result:"passed",scope:"validation and fail-closed transport"}));
})().catch(error=>{console.error(error);process.exitCode=1});
