/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Where the Python agent server lives. Defaults to the local one.
   *  A URL, never a secret -- this is compiled into the public bundle. */
  readonly VITE_AGENT_BASE?: string;
}
interface ImportMeta {
  readonly env: ImportMetaEnv;
}
