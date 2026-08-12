// HTTP 客户端封装
// 后端接入步骤：
//   1. 按 .trae/documents/quant_dashboard_tech.md 第 4 节实现 REST 接口
//   2. .env 配置 VITE_API_BASE_URL=https://your-api
//   3. 将 USE_MOCK 置为 false —— 页面零改动即可上线
export const USE_MOCK = false;

const BASE_URL: string = import.meta.env.VITE_API_BASE_URL ?? "";

export class ApiError extends Error {
  code: number;
  constructor(message: string, code: number) {
    super(message);
    this.code = code;
    this.name = "ApiError";
  }
}

export async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const isForm = init.body instanceof FormData;
  const headers: HeadersInit = {
    ...(isForm ? {} : { "Content-Type": "application/json" }),
    ...(init.headers ?? {}),
  };
  const res = await fetch(`${BASE_URL}${path}`, { ...init, headers });
  if (!res.ok) {
    let message = `HTTP ${res.status}`;
    try {
      const body = (await res.json()) as { message?: string };
      if (body?.message) message = body.message;
    } catch {
      /* 保留默认错误信息 */
    }
    throw new ApiError(message, res.status);
  }
  return res.json() as Promise<T>;
}
