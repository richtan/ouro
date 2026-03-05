import CodeBlock from "@/components/docs/CodeBlock";

const FORMULA = `price = max(
  cost_floor × margin_multiplier × demand_multiplier,
  cost_floor × 1.2,      // minimum 20% profit
  $0.01                   // absolute floor
)

cost_floor = max_gas × 1.25 + max_llm × 1.25 + nodes × minutes × $0.0006/node-min + setup_cost`;

export default function PricingPage() {
  return (
    <>
      <div className="mb-8">
        <h1 className="font-display text-2xl md:text-3xl font-bold tracking-tight text-o-text">
          Pricing
        </h1>
        <p className="text-sm text-o-textSecondary mt-1">
          Dynamic pricing engine with survival phases and demand elasticity.
        </p>
      </div>

      {/* Formula */}
      <section className="mb-10">
        <h2 className="font-display text-lg font-bold text-o-text mb-4">
          Price Formula
        </h2>
        <CodeBlock filename="pricing.py" language="python" copyText={FORMULA}>
          {FORMULA}
        </CodeBlock>
      </section>

      {/* Cost breakdown */}
      <section className="mb-10">
        <h2 className="font-display text-lg font-bold text-o-text mb-4">
          Cost Breakdown
        </h2>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          <div className="bg-o-bg rounded-lg p-3 border border-o-border">
            <div className="text-xs text-o-textSecondary uppercase tracking-wider">Gas Cost</div>
            <div className="font-display text-lg font-semibold text-o-text mt-1">~$0.002</div>
            <p className="text-xs text-o-muted mt-1">Max observed gas cost x 1.25 safety factor</p>
          </div>
          <div className="bg-o-bg rounded-lg p-3 border border-o-border">
            <div className="text-xs text-o-textSecondary uppercase tracking-wider">LLM Cost</div>
            <div className="font-display text-lg font-semibold text-o-text mt-1">~$0.008</div>
            <p className="text-xs text-o-muted mt-1">Max observed LLM inference cost x 1.25</p>
          </div>
          <div className="bg-o-bg rounded-lg p-3 border border-o-border">
            <div className="text-xs text-o-textSecondary uppercase tracking-wider">Compute</div>
            <div className="font-display text-lg font-semibold text-o-text mt-1">$0.0006</div>
            <p className="text-xs text-o-muted mt-1">Per node-minute of Slurm cluster time</p>
          </div>
        </div>
      </section>

      {/* Setup costs by mode */}
      <section className="mb-10">
        <h2 className="font-display text-lg font-bold text-o-text mb-4">
          Setup Costs by Mode
        </h2>
        <p className="text-sm text-o-textSecondary leading-relaxed mb-4">
          The <code className="font-mono text-o-accent">setup_cost</code> component varies by submission mode,
          covering workspace provisioning overhead on the Slurm cluster.
        </p>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          <div className="bg-o-bg rounded-lg p-3 border border-o-border">
            <div className="text-xs text-o-textSecondary uppercase tracking-wider">Script</div>
            <div className="font-mono text-xs text-o-text mt-1">$0.00</div>
          </div>
          <div className="bg-o-bg rounded-lg p-3 border border-o-border">
            <div className="text-xs text-o-textSecondary uppercase tracking-wider">Multi-File</div>
            <div className="font-mono text-xs text-o-text mt-1">$0.005 workspace provisioning</div>
          </div>
          <div className="bg-o-bg rounded-lg p-3 border border-o-border">
            <div className="text-xs text-o-textSecondary uppercase tracking-wider">Archive</div>
            <div className="font-mono text-xs text-o-text mt-1">$0.008 extraction + provisioning</div>
          </div>
          <div className="bg-o-bg rounded-lg p-3 border border-o-border">
            <div className="text-xs text-o-textSecondary uppercase tracking-wider">Git</div>
            <div className="font-mono text-xs text-o-text mt-1">$0.01 clone + provisioning</div>
          </div>
        </div>
      </section>

      {/* Survival phases */}
      <section className="border-t border-o-border pt-10 mb-10">
        <h2 className="font-display text-lg font-bold text-o-text mb-4">
          Survival Phases
        </h2>
        <p className="text-sm text-o-textSecondary leading-relaxed mb-4">
          The agent monitors its sustainability ratio (24h revenue / 24h costs) and adjusts
          pricing automatically. When revenue drops, margins increase to ensure survival.
        </p>
        <div className="bg-o-surface border border-o-border rounded-xl overflow-hidden overflow-x-auto">
          <table className="w-full min-w-[540px]">
            <thead>
              <tr className="text-xs text-o-muted uppercase tracking-wider border-b border-o-border bg-o-bg">
                <th className="text-left px-4 py-2.5">Phase</th>
                <th className="text-left px-4 py-2.5">Ratio</th>
                <th className="text-left px-4 py-2.5">Margin</th>
                <th className="text-left px-4 py-2.5">Heartbeat</th>
              </tr>
            </thead>
            <tbody>
              <tr className="text-sm border-t border-o-border">
                <td className="px-4 py-2.5">
                  <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-xs font-mono bg-o-green/10 text-o-green">
                    OPTIMAL
                  </span>
                </td>
                <td className="px-4 py-2.5 font-mono text-xs text-o-text">&ge; 1.5</td>
                <td className="px-4 py-2.5 font-mono text-xs text-o-text">1.0x</td>
                <td className="px-4 py-2.5 text-xs text-o-textSecondary">60 min</td>
              </tr>
              <tr className="text-sm border-t border-o-border">
                <td className="px-4 py-2.5">
                  <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-xs font-mono bg-o-blue/10 text-o-blueText">
                    CAUTIOUS
                  </span>
                </td>
                <td className="px-4 py-2.5 font-mono text-xs text-o-text">&ge; 1.0</td>
                <td className="px-4 py-2.5 font-mono text-xs text-o-text">1.1x</td>
                <td className="px-4 py-2.5 text-xs text-o-textSecondary">120 min</td>
              </tr>
              <tr className="text-sm border-t border-o-border">
                <td className="px-4 py-2.5">
                  <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-xs font-mono bg-o-amber/10 text-o-amber">
                    SURVIVAL
                  </span>
                </td>
                <td className="px-4 py-2.5 font-mono text-xs text-o-text">&ge; 0.5</td>
                <td className="px-4 py-2.5 font-mono text-xs text-o-text">1.3x</td>
                <td className="px-4 py-2.5 text-xs text-o-textSecondary">Off</td>
              </tr>
              <tr className="text-sm border-t border-o-border">
                <td className="px-4 py-2.5">
                  <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-xs font-mono bg-o-red/10 text-o-red">
                    CRITICAL
                  </span>
                </td>
                <td className="px-4 py-2.5 font-mono text-xs text-o-text">&lt; 0.5</td>
                <td className="px-4 py-2.5 font-mono text-xs text-o-text">3.0x</td>
                <td className="px-4 py-2.5 text-xs text-o-textSecondary">Off</td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>

      {/* Demand multiplier */}
      <section className="border-t border-o-border pt-10">
        <h2 className="font-display text-lg font-bold text-o-text mb-4">
          Demand Multiplier
        </h2>
        <p className="text-sm text-o-textSecondary leading-relaxed mb-4">
          Price adjusts based on recent job volume (jobs in the last hour):
        </p>
        <div className="bg-o-surface border border-o-border rounded-xl overflow-hidden overflow-x-auto">
          <table className="w-full min-w-[400px]">
            <thead>
              <tr className="text-xs text-o-muted uppercase tracking-wider border-b border-o-border bg-o-bg">
                <th className="text-left px-4 py-2.5">Jobs / Hour</th>
                <th className="text-left px-4 py-2.5">Multiplier</th>
                <th className="text-left px-4 py-2.5">Effect</th>
              </tr>
            </thead>
            <tbody>
              <tr className="text-sm border-t border-o-border">
                <td className="px-4 py-2.5 font-mono text-xs text-o-text">0</td>
                <td className="px-4 py-2.5 font-mono text-xs text-o-text">0.8x</td>
                <td className="px-4 py-2.5 text-xs text-o-textSecondary">20% discount to attract jobs</td>
              </tr>
              <tr className="text-sm border-t border-o-border">
                <td className="px-4 py-2.5 font-mono text-xs text-o-text">1-3</td>
                <td className="px-4 py-2.5 font-mono text-xs text-o-text">1.0x</td>
                <td className="px-4 py-2.5 text-xs text-o-textSecondary">Standard pricing</td>
              </tr>
              <tr className="text-sm border-t border-o-border">
                <td className="px-4 py-2.5 font-mono text-xs text-o-text">4+</td>
                <td className="px-4 py-2.5 font-mono text-xs text-o-text">1.0 + 0.15 per job</td>
                <td className="px-4 py-2.5 text-xs text-o-textSecondary">Surge pricing under high demand</td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>
    </>
  );
}
