import type { Principal } from '@dfinity/principal';
import type { ActorMethod } from '@dfinity/agent';
import type { IDL } from '@dfinity/candid';

export interface _SERVICE {
  'test_fs_diagnostics' : ActorMethod<[], Array<string>>,
  'test_fs_mkdir' : ActorMethod<[], Array<string>>,
  'test_fs_nested_mkdir' : ActorMethod<[], Array<string>>,
  'test_fs_path_exists' : ActorMethod<[], Array<string>>,
  'test_fs_rename' : ActorMethod<[], Array<string>>,
  'test_fs_rmdir' : ActorMethod<[], Array<string>>,
}
export declare const idlFactory: IDL.InterfaceFactory;
export declare const init: (args: { IDL: typeof IDL }) => IDL.Type[];
