export const idlFactory = ({ IDL }) => {
  return IDL.Service({
    'test_fs_diagnostics' : IDL.Func([], [IDL.Vec(IDL.Text)], []),
    'test_fs_mkdir' : IDL.Func([], [IDL.Vec(IDL.Text)], []),
    'test_fs_nested_mkdir' : IDL.Func([], [IDL.Vec(IDL.Text)], []),
    'test_fs_path_exists' : IDL.Func([], [IDL.Vec(IDL.Text)], []),
    'test_fs_rename' : IDL.Func([], [IDL.Vec(IDL.Text)], []),
    'test_fs_rmdir' : IDL.Func([], [IDL.Vec(IDL.Text)], []),
  });
};
export const init = ({ IDL }) => { return []; };
