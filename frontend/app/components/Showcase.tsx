"use client";

import type { Finding, Showcase as ShowcaseData, Subscription } from "../api";
import { leadFlag, money, reclaimable, shortDate } from "../format";
import { CardBody, CardContainer, CardItem } from "./ui/3d-card";

// The three workflows the dashboard leads with, each on a card that tilts toward the pointer (Aceternity's 3D card).
// One button per card opens its workflow in the detail pane. Yellow only marks money you can get back.

type Open = (kind: "sub" | "finding", id: string, action?: "cancel" | "prepare") => void;

export default function Showcase({ data, subs, findings, onOpen }: {
  data: ShowcaseData | null;
  subs: Subscription[];
  findings: Finding[];
  onOpen: Open;
}) {
  if (!data) return null;
  const gym = subs.find((s) => s.id === data.gym?.sub_id);
  const streaming = subs.find((s) => s.id === data.streaming?.sub_id);
  const drop = findings.find((f) => f.id === data.price?.finding_id);
  const watch = data.price?.watch ?? null;
  if (!gym && !streaming && !drop && !watch) return null;

  return (
    <section className="showcase" aria-label="Three ways ClawBack gets your money back">
      {gym && (
        <WorkflowCard
          title="Stop paying for a gym you don't go to"
          merchant={gym.merchant}
          line={gym.usage.evidence[0]?.split(": ").slice(1).join(": ") || leadFlag(gym)?.message || ""}
          money={<>Save <span className="hl">{money(reclaimable(gym) || gym.monthly_cost)}</span> a month</>}
          action={gym.status === "cancel_pending" ? "Cancellation sent" : "Write and send the email"}
          disabled={gym.status === "cancel_pending"}
          onClick={() => onOpen("sub", gym.id, "cancel")}
        />
      )}
      {streaming && (
        <WorkflowCard
          title="Cancel what you don't watch"
          merchant={streaming.merchant}
          line={leadFlag(streaming)?.message ?? ""}
          money={<>Save <span className="hl">{money(reclaimable(streaming) || streaming.monthly_cost)}</span> a month</>}
          action={streaming.status === "cancel_pending" ? "Cancelling" : `Cancel on ${streaming.merchant}`}
          disabled={streaming.status === "cancel_pending"}
          onClick={() => onOpen("sub", streaming.id, "cancel")}
        />
      )}
      {drop && (
        <WorkflowCard
          title="Get the price drop back"
          merchant={`${drop.merchant}: ${drop.price_check?.item ?? ""}`}
          line={drop.price_check
            ? `Paid ${money(drop.price_check.paid)}. Today ${money(drop.price_check.now)}`
              + (drop.price_check.how === "live" ? ` on ${hostOf(drop.price_check.url ?? "")}.` : " (simulated price).")
            : drop.message}
          money={<>Get <span className="hl">{money(drop.amount)}</span> back by {shortDate(drop.deadline)}</>}
          action="See the purchase and ask"
          onClick={() => onOpen("finding", drop.id, undefined)}
        />
      )}
      {!drop && watch && (
        <WorkflowCard
          title="Watching your price drop window"
          merchant={`${watch.store}: ${watch.item}`}
          line={`Paid ${money(watch.paid)}. Today ${money(watch.price_now)}${watch.how === "live" ? ` on ${hostOf(watch.url ?? "")}` : ""}.`}
          money={<>No drop today. ClawBack checks every day until {shortDate(watch.deadline)}.</>}
          action="Nothing to do yet"
          disabled
          onClick={() => {}}
        />
      )}
    </section>
  );
}

function WorkflowCard({ title, merchant, line, money: amount, action, disabled, onClick }: {
  title: string; merchant: string; line: string; money: React.ReactNode; action: string; disabled?: boolean;
  onClick: () => void;
}) {
  return (
    <CardContainer containerClassName="py-0 w-full" className="w-full">
      <CardBody className="workflow-card group/card relative h-auto w-full rounded-[3px] border border-[var(--rule)] bg-[var(--sheet)] p-5 transition-shadow hover:shadow-xl hover:shadow-black/40">
        <CardItem translateZ={30} as="h3" className="workflow-title">{title}</CardItem>
        <CardItem translateZ={50} as="p" className="workflow-merchant">{merchant}</CardItem>
        <CardItem translateZ={40} as="p" className="workflow-line">{line}</CardItem>
        <div className="workflow-foot">
          <CardItem translateZ={60} as="p" className="workflow-money">{amount}</CardItem>
          <CardItem translateZ={40} as="button" className="solid" disabled={disabled} onClick={onClick}>
            {action}
          </CardItem>
        </div>
      </CardBody>
    </CardContainer>
  );
}

function hostOf(url: string) {
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return "the store's site";
  }
}
