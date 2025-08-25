function bench_matlab(opts)

    arguments
        opts.oneshot   logical = false
        opts.full_test logical = false
    end

    if opts.oneshot
        bench_cpus = maxNumCompThreads();
    else
        maxncpus = maxNumCompThreads();
        persist_onCleanup_return = onCleanup(@() maxNumCompThreads(maxncpus));
        if maxNumCompThreads()>=4
            bench_cpus = [1, maxNumCompThreads()/2, maxNumCompThreads()];
        else
            bench_cpus = [1, maxNumCompThreads()];
        end
    end

    if opts.full_test
        bench_size = [1024, 6144];
        bench_num  = [100 , 10];
    else
        bench_size = 1024;
        bench_num  = 100;
    end

    print_sys_info()

    for k = 1:length(bench_size)
        run_bench(bench_size(k), bench_cpus, bench_num(k));
    end
end


function print_sys_info()
    fprintf("MATLAB version %s, built on %s\n", version(), version("-date"));
    fprintf(" - BLAS:   ""%s""\n", version("-blas"));
    fprintf(" - LAPACK: ""%s""\n", version("-lapack"));
    fprintf(newline());
end


function run_bench(n, bench_cpus, max_bench_num)

    sdim = 10; % for svds and sparse rdivide
    rstream = RandStream("mt19937ar", "Seed", 0); % use fixed rand seed for reproductivity

    A = 2 + randn(rstream, n, "double");
    B = A * diag([100*randn(rstream, 1, 2*sdim), randn(rstream, 1, n-2*sdim)]) / A;

    ss = floor(sqrt(n));
    d0 = 100 + randn(rstream, n, 1);
    d1 = randn(rstream, n+1, 1);
    ds = randn(rstream, n+ss, 1);
    d0 = (abs(d1(1:(end-1))) + abs(ds(1:(end-ss)))) + abs(d0);

    spR = spdiags( ...
        [d0, d1(1:(end-1)), ds(1:(end-ss))], ...
        [0, 1, ss], ...
        n, n ...
    );

    spA = spR' * spR;

    % [~, cf] = chol(spA);
    % assert(cf==0); % positive definite
    % assert(isequal(spA, spA')); % Hermitian


    bench_func = {};

    % Algebraic Operation
    bench_func = [bench_func, {func_partial(@ubench, @() (A./(1+sqrt(A))).*B, num=max_bench_num)}];

    % SVDs
    bench_func = [bench_func, {func_partial(@ubench, @() svds(B, sdim), num=max_bench_num)}];

    % Eigens
    bench_func = [bench_func, {func_partial(@ubench, @() eigs(B, sdim), num=max_bench_num)}];

    % Sparse rdivide
    bench_func = [bench_func, {func_partial(@ubench, @() (spR \ (spR' \ A)), num=max_bench_num)}];

    % Sparse svds
    bench_func = [bench_func, {func_partial(@ubench, @() svds(spA, sdim), num=max_bench_num)}];

    % Sparse eigs
    bench_func = [bench_func, {func_partial(@ubench, @() eigs(spA, sdim), num=max_bench_num)}];


    bench_name = ["Algebra", sprintf("svds(A, %d)", sdim), sprintf("eigs(A, %d)", sdim), "spA \ A", sprintf("svds(spA, %d)", sdim), sprintf("eigs(spA, %d)", sdim)];
    bench_len  = length(bench_func);

    assert(bench_len == length(bench_name));


    bench_cpus = sort(bench_cpus);
    best_data = nan(length(bench_cpus), bench_len);
    counter = 0;

    for ncpus = bench_cpus

        fprintf("bench size = %d, using %d cpu(s)...\n", n, ncpus);
        counter = counter + 1;

        maxNumCompThreads(ncpus);
        data = nan(3, bench_len);

        for k = 1:bench_len
            foo = bench_func{k};

            fprintf(" > running bench for %s\n", bench_name(k));
            %     best        mean        std
            try
                [data(1, k), data(2, k), data(3, k)] = foo();
            catch ME
                disp(ME);
            end
            best_data(counter, k) = data(1, k);
        end

        print_results(bench_len, bench_name, data, "op/s");
    end


    info_str = "Speed up between 1 &";
    bnshift = 2;
    mbnl = max(max(strlength(bench_name))+bnshift, strlength(info_str));
    if length(bench_cpus) > 1
        fprintf(newline());
        fprintf(sprintf("%-"+num2str(mbnl)+"s", info_str) + sprintf("%6d", bench_cpus(2:end)) + "  cpus:\n");
        for k = 1:bench_len                  % ":" add to bench_name take one width
            fprintf("  %-"+num2str(mbnl-bnshift)+"s "+sprintf("x%-5.2f", best_data(2:end, k) ./ best_data(1, k))+newline(), bench_name(k)+":");
        end
        fprintf(newline());
    end

end


function print_results(len, name, data, unit)

    unit = sprintf("(%s)", unit);

    ystrs = ["best ", "avg  ", "std  "];
    ylen  = max(max(strlength(ystrs)), strlength(unit));
    tlen  = max(strlength(name));

    yfmt = sprintf("  │ %%%ds ", ylen);
    tfmt = sprintf("│ %%%ds ", tlen);

    fprintf("results:\n");

    fprintf(yfmt, unit);
    for k = 1:len
        fprintf(tfmt, name(k));
    end

    for k = 1:3
        fprintf("│");
        fprintf(newline());

        fprintf(yfmt, ystrs(k));
        for tk = 1:len
            fprintf(tfmt, sprintf("%.2f", data(k, tk)));
        end
    end

    fprintf("│"+newline());
    fprintf(newline());

end


function [ops_best, ops_mean, ops_std] = ubench(foo, opts)

    arguments
        foo function_handle
        opts.num = 100
        opts.repeat = 1
    end

    t = nan(1, opts.num);
    for n = 1:opts.num
        t_start = tic;
        for k = 1:opts.repeat
            foo();
        end
        t(n) = toc(t_start);
    end

    ops = 1 ./ t;

    ops_best = max(ops, [], "all");
    ops_mean = mean(ops);
    ops_std  = std(ops);

end


function handler = func_partial(varargin)

    if nargin==0
        error("usage: new_func = functools.partial(@func, param1, param2, ...), where new_func(new_param1, new_param2, ...) <-> func(param1, param2, ..., new_param1, new_param2, ...)");
    end

    foo = varargin{1};
    if ~isa(foo, "function_handle")
        error("functools.partial expects ""function_handle"" but got ""%s""", class(foo));
    end

    if nargin==1
        warning("new_func = functools.partial(@func) is equal to new_func = @func");
        handler = foo;
        return
    end

    freeze_params = varargin(2:end);

    function varargout = wrapper_func(varargin)
        [varargout{1:nargout}] = foo(freeze_params{:}, varargin{:});
    end

    handler = @wrapper_func;
end