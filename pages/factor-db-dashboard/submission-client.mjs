export const BUCKET = "factor-private-submissions";
const MIME = {py:"text/x-python",json:"application/json",md:"text/markdown",
  pdf:"application/pdf",csv:"text/csv",parquet:"application/octet-stream"};
const FIELDS = ["factor_id","version","title","formula","license","code_hash","config_hash",
  "data_hash","metrics","blockers","verification_stage"];

export function validateFile(file, currentBytes) {
  if (!file || typeof file.name !== "string" || file.name.length > 160 ||
      /[\\/:]|[\x00-\x1f]|\.\./.test(file.name) || !Number.isSafeInteger(file.size) ||
      file.size < 1 || file.size > 25 * 1024 * 1024 || currentBytes + file.size > 100 * 1024 * 1024) {
    throw new Error("文件名或大小不合法：每文件最多25MB，每版本最多100MB");
  }
  const type = MIME[file.name.split(".").pop().toLowerCase()];
  if (!type) throw new Error("只接受 py/json/md/pdf/csv/parquet，不接受压缩包或二进制程序");
  return type;
}

export function draftPayload(input) {
  if (!input || Object.keys(input).some(k => !FIELDS.includes(k))) throw new Error("不允许指定所有者、状态或角色");
  if (!/^[A-Za-z0-9_.:-]{1,160}$/.test(input.factor_id || "") ||
      !Number.isInteger(input.version) || input.version < 1 || input.version > 999999 ||
      !["implemented","partial_proof","internal_validated"].includes(input.verification_stage)) {
    throw new Error("因子标识、版本或验证阶段不合法");
  }
  for (const [key, max] of [["title",200],["formula",4000],["license",4000]]) {
    if (typeof input[key] !== "string" || !input[key].trim() || input[key].length > max) throw new Error("必填字段缺失或过长");
  }
  for (const key of ["code_hash","config_hash","data_hash"]) {
    if (input[key] && !/^[0-9a-f]{64}$/.test(input[key])) throw new Error("需要小写SHA256指纹");
  }
  if (!input.metrics || typeof input.metrics !== "object" || Array.isArray(input.metrics) ||
      !Array.isArray(input.blockers) || new TextEncoder().encode(JSON.stringify(input)).length > 262144) {
    throw new Error("指标或验证缺口不合法");
  }
  return Object.fromEntries(FIELDS.map(k => [k, input[k] ?? ""]));
}

export async function fileDigest(blob) {
  const hash = await crypto.subtle.digest("SHA-256", await blob.arrayBuffer());
  return [...new Uint8Array(hash)].map(v => v.toString(16).padStart(2,"0")).join("");
}

export class PrivateFactorClient {
  constructor(client) { this.client = client; }
  async rpc(name, payload) {
    const { data, error } = await this.client.rpc(name, payload);
    if (error) throw new Error(error.message);
    return data;
  }
  create(payload) { return this.rpc("pf_create", {p_payload:draftPayload(payload)}); }
  update(id, payload) { return this.rpc("pf_update", {p_id:id,p_payload:draftPayload(payload)}); }
  submit(id) { return this.rpc("pf_submit", {p_id:id}); }
  beginReview(id) { return this.rpc("pf_begin_review", {p_id:id}); }
  review(id, decision, note, attestation) {
    return this.rpc("pf_review", {p_id:id,p_decision:decision,p_note:note,p_attestation:attestation});
  }
  async list() {
    const { data, error } = await this.client.from("pf_submissions").select("*").order("created_at",{ascending:false});
    if (error) throw new Error(error.message);
    return data;
  }
  async related(table, id) {
    if (!["pf_files","pf_reviews","pf_audit"].includes(table)) throw new Error("不允许的数据源");
    const { data, error } = await this.client.from(table).select("*").eq("submission_id",id);
    if (error) throw new Error(error.message);
    return data;
  }
  async upload(id, file, currentBytes) {
    const contentType = validateFile(file, currentBytes);
    const sha256 = await fileDigest(file);
    const reserved = await this.rpc("pf_reserve_file", {p_id:id,p_name:file.name,p_size:file.size,p_sha256:sha256});
    return this.finishUpload(reserved, file, contentType);
  }
  async finishUpload(reserved, file, contentType = validateFile(file, 0)) {
    if (file.name !== reserved.name || file.size !== reserved.size_bytes ||
        await fileDigest(file) !== reserved.sha256) throw new Error("文件与预约指纹不符");
    const { error } = await this.client.storage.from(BUCKET).upload(reserved.object_path,file,
      {contentType,upsert:false});
    if (error) {
      // A prior successful upload may have lost its finalization response.
      if (!["409","Duplicate"].includes(String(error.statusCode || error.error))) throw new Error(error.message);
    }
    return this.rpc("pf_finish_file",{p_file_id:reserved.id});
  }
  async download(file) {
    const { data, error } = await this.client.storage.from(BUCKET).download(file.object_path);
    if (error) throw new Error(error.message);
    if (data.size !== file.size_bytes || await fileDigest(data) !== file.sha256) throw new Error("附件大小或指纹不一致");
    return data;
  }
  checkFile(file, note) {
    return this.rpc("pf_check_file",{p_file_id:file.id,p_sha256:file.sha256,p_note:note});
  }
}
