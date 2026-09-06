-- ==============================================================================
-- EvalForge: Seed Initial Scoring Rubric v1.0.0
-- Version: 1.0.0
-- Description: Seeds the initial scoring rubric and 10 evaluation categories,
--              including detailed criteria rubrics, deterministic tool mappings,
--              and a database assertion verifying that all weights sum to 100.
-- ==============================================================================

-- 1. Insert Initial Rubric Version 1.0.0
INSERT INTO scoring_rubrics (version, name, description, total_weight, is_active, metadata)
VALUES (
    '1.0.0',
    'Standard Production Software Evaluation Rubric',
    'Evidence-backed deterministic and qualitative evaluation standard for open-source and web applications.',
    100.00,
    true,
    jsonb_build_object(
        'created_by', 'EvalForge Architecture Committee',
        'principles', jsonb_build_array(
            'Deterministic tools for objective measurements',
            'Structured LLMs for qualitative synthesis and interpretation',
            'Verified web research with citations for novelty claims',
            'Explicit unmeasurable tags instead of inflated scores'
        )
    )
)
ON CONFLICT (version) DO UPDATE 
SET name = EXCLUDED.name,
    description = EXCLUDED.description,
    total_weight = EXCLUDED.total_weight,
    is_active = EXCLUDED.is_active,
    metadata = EXCLUDED.metadata,
    updated_at = NOW();

-- 2. Insert the 10 Evaluation Categories (Strictly summing to 100.00)
INSERT INTO rubric_categories (
    rubric_version,
    category_key,
    name,
    description,
    weight,
    evaluator_name,
    criteria_rubric
) VALUES
(
    '1.0.0',
    'problem_statement',
    'Problem Statement',
    'Clarity, real-world relevance, scope definition, and target audience alignment of the problem being solved.',
    10.00,
    'ProblemAnalyzer',
    jsonb_build_object(
        'min_score', 0,
        'max_score', 10,
        'measurement_type', 'qualitative_llm',
        'evaluation_focus', jsonb_build_array(
            'Explicit problem definition in README or project documentation',
            'Real-world significance and utility',
            'Identified pain point and target persona/stakeholder'
        ),
        'scoring_bands', jsonb_build_object(
            'excellent', '9-10: Problem is acutely defined with clear pain points, target audience, and quantified impact.',
            'proficient', '7-8: Well-articulated problem with clear goals, minor omissions in scope or target persona.',
            'adequate', '5-6: Problem stated generally without concrete constraints or user workflows.',
            'deficient', '0-4: Vague, missing, or purely tautological description of the project purpose.'
        )
    )
),
(
    '1.0.0',
    'solution_quality',
    'Solution Quality',
    'Soundness of technical architecture, system design, domain modeling, and appropriateness of tech stack.',
    15.00,
    'SolutionAnalyzer',
    jsonb_build_object(
        'min_score', 0,
        'max_score', 15,
        'measurement_type', 'qualitative_llm',
        'evaluation_focus', jsonb_build_array(
            'Cohesion and separation of concerns',
            'API design and data contract clarity',
            'Fitness of framework/libraries chosen for the stated problem'
        ),
        'scoring_bands', jsonb_build_object(
            'excellent', '13-15: Exceptional modular architecture, crisp interfaces, defensible technology trade-offs.',
            'proficient', '10-12: Strong technical structure with good separation of concerns and appropriate stack.',
            'adequate', '7-9: Working solution but with tight coupling or questionable architecture choices.',
            'deficient', '0-6: Spaghetti architecture, inappropriate technologies, or monolithic design anti-patterns.'
        )
    )
),
(
    '1.0.0',
    'code_quality',
    'Code Quality',
    'Deterministic syntax conformance, formatting consistency, AST complexity, and static analysis health.',
    15.00,
    'CodeQualityAnalyzer',
    jsonb_build_object(
        'min_score', 0,
        'max_score', 15,
        'measurement_type', 'deterministic_tools',
        'tools', jsonb_build_array('eslint', 'prettier', 'ruff', 'ast_complexity'),
        'evaluation_focus', jsonb_build_array(
            'Zero critical linting/formatting errors',
            'Low cyclomatic complexity per function',
            'Consistent naming conventions and code readability'
        ),
        'scoring_bands', jsonb_build_object(
            'excellent', '13-15: 0 linter errors, standard formatting across 100% of files, low AST complexity.',
            'proficient', '10-12: < 5 minor style warnings, 0 critical syntax errors, manageable complexity.',
            'adequate', '7-9: Moderate number of lint warnings or occasional formatting irregularities.',
            'deficient', '0-6: Pervasive linter failures, unformatted code, or extreme cyclomatic complexity.'
        )
    )
),
(
    '1.0.0',
    'optimization',
    'Optimization',
    'Resource efficiency, memory management, bundle size awareness, and algorithmic complexity.',
    10.00,
    'OptimizationAnalyzer',
    jsonb_build_object(
        'min_score', 0,
        'max_score', 10,
        'measurement_type', 'hybrid_ast_llm',
        'evaluation_focus', jsonb_build_array(
            'Algorithmic time and space complexity in hot loops/data operations',
            'Unnecessary re-renders, bundle bloat, or memory leaks',
            'Data fetching caching, indexing, or pagination strategies'
        ),
        'scoring_bands', jsonb_build_object(
            'excellent', '9-10: Efficient algorithms, lazy loading, caching layers, optimized assets/dependencies.',
            'proficient', '7-8: Good resource hygiene with minor unoptimized paths that do not impact scalability.',
            'adequate', '5-6: Unbounded queries, lack of pagination, or naive algorithmic implementations.',
            'deficient', '0-4: Critical performance bottlenecks (O(N^2) in request paths, severe memory leaks).'
        )
    )
),
(
    '1.0.0',
    'ui_ux',
    'UI/UX',
    'Visual polish, responsive viewports, design system consistency, keyboard accessibility, and state feedback.',
    10.00,
    'UIAnalyzer',
    jsonb_build_object(
        'min_score', 0,
        'max_score', 10,
        'measurement_type', 'deterministic_playwright',
        'evaluation_focus', jsonb_build_array(
            'Responsive layout reflow across mobile, tablet, and desktop viewports',
            'Visible focus states and accessible color contrast (4.5:1 minimum)',
            'No layout shifts or clipped interactive elements'
        ),
        'scoring_bands', jsonb_build_object(
            'excellent', '9-10: Cohesive design tokens, fluid responsiveness, robust focus states, rich feedback.',
            'proficient', '7-8: Clean UI that renders well on all standard viewports with good contrast.',
            'adequate', '5-6: Functional interface but suffers from occasional viewport overflow or weak hierarchy.',
            'deficient', '0-4: Broken mobile layouts, illegible text contrast, missing hover/focus indicators.'
        )
    )
),
(
    '1.0.0',
    'performance',
    'Performance',
    'Empirical Core Web Vitals, server response times (TTFB), Lighthouse performance audit, and asset size.',
    10.00,
    'PerformanceAnalyzer',
    jsonb_build_object(
        'min_score', 0,
        'max_score', 10,
        'measurement_type', 'deterministic_lighthouse',
        'tools', jsonb_build_array('lighthouse', 'curl_timing'),
        'evaluation_focus', jsonb_build_array(
            'Lighthouse Performance score (FCP, LCP, CLS, TBT)',
            'Time to First Byte (TTFB) < 800ms',
            'Optimized payload sizes and asset compression'
        ),
        'scoring_bands', jsonb_build_object(
            'excellent', '9-10: Lighthouse 90-100, sub-second LCP, 0 CLS, rapid TTFB.',
            'proficient', '7-8: Lighthouse 75-89, good interactive responsiveness.',
            'adequate', '5-6: Lighthouse 50-74, noticeable latency on resource loading.',
            'deficient', '0-4: Lighthouse < 50 or severe blocking scripts.'
        )
    )
),
(
    '1.0.0',
    'security',
    'Security',
    'Static vulnerability scanning (SAST), dependency CVE audits, secret leakage detection, and sanitization.',
    10.00,
    'SecurityAnalyzer',
    jsonb_build_object(
        'min_score', 0,
        'max_score', 10,
        'measurement_type', 'deterministic_sast',
        'tools', jsonb_build_array('semgrep', 'bandit', 'npm_audit', 'trufflehog_patterns'),
        'evaluation_focus', jsonb_build_array(
            'Zero hardcoded API keys, secrets, or credentials',
            'Zero known critical/high CVEs in declared dependencies',
            'Sanitization of untrusted inputs (SQLi, XSS, command injection)'
        ),
        'scoring_bands', jsonb_build_object(
            'excellent', '9-10: 0 secrets, 0 high/critical CVEs, clean SAST scan, strong input sanitization.',
            'proficient', '7-8: 0 secrets, low/moderate vulnerabilities with known patches, good basic defenses.',
            'adequate', '5-6: Unpatched non-critical dependencies or missing CSP/security headers.',
            'deficient', '0-4: Hardcoded credentials, critical CVEs, or blatant injection vulnerabilities.'
        )
    )
),
(
    '1.0.0',
    'novelty',
    'Innovation/Novelty',
    'Originality of technical approach, differentiation from existing solutions, and verified market novelty.',
    5.00,
    'NoveltyAnalyzer',
    jsonb_build_object(
        'min_score', 0,
        'max_score', 5,
        'measurement_type', 'verified_web_research',
        'mandatory_requirement', 'Real external citations and URLs for every comparative claim',
        'evaluation_focus', jsonb_build_array(
            'Novel approach to an established problem OR creative new capability',
            'Clear differentiation from published GitHub projects and commercial alternatives',
            'Documented evidence and citations for prior art'
        ),
        'scoring_bands', jsonb_build_object(
            'excellent', '5: Truly inventive methodology or novel intersection of technologies with strong citations.',
            'proficient', '4: Solid differentiated feature set with clear advantages over cited alternatives.',
            'adequate', '2-3: Standard re-implementation of existing pattern with incremental changes.',
            'deficient', '0-1: Direct tutorial replica or verbatim fork with no innovation.'
        )
    )
),
(
    '1.0.0',
    'documentation',
    'Documentation',
    'Completeness of README, architecture diagrams, local setup instructions, inline comments, and API specs.',
    5.00,
    'DocumentationAnalyzer',
    jsonb_build_object(
        'min_score', 0,
        'max_score', 5,
        'measurement_type', 'hybrid_static_llm',
        'evaluation_focus', jsonb_build_array(
            'Detailed README with installation, usage, and configuration guides',
            'Clear architecture explanation or system diagram',
            'Inline docstrings and typed function signatures for public interfaces'
        ),
        'scoring_bands', jsonb_build_object(
            'excellent', '5: Comprehensive documentation, quick-start, architecture overview, and full API docs.',
            'proficient', '4: Clear README with working setup instructions and good inline documentation.',
            'adequate', '2-3: Minimal README with basic description but missing setup details or troubleshooting.',
            'deficient', '0-1: Empty or default template README, zero documentation.'
        )
    )
),
(
    '1.0.0',
    'engineering_practices',
    'Engineering Practices',
    'CI/CD pipeline presence, automated test coverage, environment configuration hygiene, and git commit quality.',
    10.00,
    'EngineeringAnalyzer',
    jsonb_build_object(
        'min_score', 0,
        'max_score', 10,
        'measurement_type', 'deterministic_filesystem',
        'evaluation_focus', jsonb_build_array(
            'Automated test suites (unit, integration, or e2e tests)',
            'CI/CD automation workflows (GitHub Actions, GitLab CI, etc.)',
            '.gitignore, lockfiles, and environment template (.env.example) hygiene',
            'Atomic, descriptive git commit messages'
        ),
        'scoring_bands', jsonb_build_object(
            'excellent', '9-10: Automated test suite, green CI workflow, clean git history, crisp configuration templates.',
            'proficient', '7-8: Tests present and runnable, basic CI workflow configured, proper .gitignore.',
            'adequate', '5-6: Ad-hoc testing files without CI integration or messy git commit history.',
            'deficient', '0-4: No tests, no CI/CD, committed node_modules/binaries, or chaotic commits.'
        )
    )
)
ON CONFLICT (rubric_version, category_key) DO UPDATE
SET name = EXCLUDED.name,
    description = EXCLUDED.description,
    weight = EXCLUDED.weight,
    evaluator_name = EXCLUDED.evaluator_name,
    criteria_rubric = EXCLUDED.criteria_rubric,
    updated_at = NOW();

-- ==============================================================================
-- 3. VALIDATE DATABASE INTEGRITY & WEIGHTS SUM (EXACTLY 100.00)
-- ==============================================================================

DO $$
DECLARE
    sum_weights NUMERIC(5,2);
    expected_sum NUMERIC(5,2) := 100.00;
    rubric_rec RECORD;
BEGIN
    FOR rubric_rec IN SELECT version, total_weight FROM scoring_rubrics LOOP
        SELECT COALESCE(SUM(weight), 0.00) INTO sum_weights
        FROM rubric_categories
        WHERE rubric_version = rubric_rec.version;

        IF sum_weights != rubric_rec.total_weight THEN
            RAISE EXCEPTION 'DATABASE INTEGRITY VIOLATION: Rubric % categories sum to %, but expected %', 
                rubric_rec.version, sum_weights, rubric_rec.total_weight;
        END IF;

        RAISE NOTICE 'SUCCESS: Rubric % categories verified. Total Weight = %', 
            rubric_rec.version, sum_weights;
    END LOOP;
END $$;
