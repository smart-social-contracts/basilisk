import { Test } from 'azle/test';
import { _SERVICE } from './dfx_generated/filesystem/filesystem.did';
import { ActorSubclass } from '@dfinity/agent';
import { execSync } from 'child_process';

export function getTests(actor: ActorSubclass<_SERVICE>): Test[] {
    return [
        {
            name: 'test_fs_diagnostics',
            test: async () => {
                const result = await actor.test_fs_diagnostics();
                console.log('DIAGNOSTICS:', JSON.stringify(result, null, 2));
                return {
                    Ok: result.length > 0
                };
            }
        },
        {
            name: 'test_fs_mkdir',
            test: async () => {
                const result = await actor.test_fs_mkdir();
                console.log('mkdir result:', JSON.stringify(result));
                // mkdir=OK, is_dir=True
                return {
                    Ok: (result[0] === 'mkdir=OK' || result[0] === 'mkdir=EXISTS') &&
                        result[1] === 'is_dir=True'
                };
            }
        },
        {
            name: 'test_fs_path_exists',
            test: async () => {
                const result = await actor.test_fs_path_exists();
                console.log('path_exists result:', JSON.stringify(result));
                // [exists=True, nonexistent=False, isdir=True]
                return {
                    Ok:
                        result[0] === 'True' &&
                        result[1] === 'False' &&
                        result[2] === 'True'
                };
            }
        },
        {
            name: 'test_fs_rename',
            test: async () => {
                const result = await actor.test_fs_rename();
                console.log('rename result:', JSON.stringify(result));
                // [old=False, new=True]
                return {
                    Ok:
                        result[0] === 'False' &&
                        result[1] === 'True'
                };
            }
        },
        {
            name: 'test_fs_rmdir',
            test: async () => {
                const result = await actor.test_fs_rmdir();
                console.log('rmdir result:', JSON.stringify(result));
                // [before=True, after=False]
                return {
                    Ok:
                        result[0] === 'True' &&
                        result[1] === 'False'
                };
            }
        },
        {
            name: 'test_fs_nested_mkdir',
            test: async () => {
                const result = await actor.test_fs_nested_mkdir();
                console.log('nested_mkdir result:', JSON.stringify(result));
                // all True
                return {
                    Ok: result.every((v: string) => v === 'True')
                };
            }
        },
        {
            name: 'test_fs_persistence: write file before upgrade',
            test: async () => {
                const result = await actor.write_file(
                    '/persist_test/hello.txt',
                    'Hello from before upgrade!'
                );
                console.log('write_file result:', result);
                return {
                    Ok: result === 'OK'
                };
            }
        },
        {
            name: 'test_fs_persistence: verify file readable before upgrade',
            test: async () => {
                const result = await actor.read_file('/persist_test/hello.txt');
                console.log('read_file before upgrade:', result);
                return {
                    Ok: result === 'Hello from before upgrade!'
                };
            }
        },
        {
            name: 'test_fs_persistence: upgrade canister',
            test: async () => {
                try {
                    execSync(
                        `dfx deploy filesystem --upgrade-unchanged`,
                        { stdio: 'inherit' }
                    );
                    return { Ok: true };
                } catch (e) {
                    console.error('upgrade failed:', e);
                    return { Ok: false };
                }
            }
        },
        {
            name: 'test_fs_persistence: read file after upgrade',
            test: async () => {
                const result = await actor.read_file('/persist_test/hello.txt');
                console.log('read_file after upgrade:', result);
                return {
                    Ok: result === 'Hello from before upgrade!'
                };
            }
        }
    ];
}
