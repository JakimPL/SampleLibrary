import type { ReactElement, ReactNode } from "react";
import { useNavigate } from "react-router-dom";

import { useModule } from "../../modules/useModule";
import { useSampleDetail } from "../../samples/useSampleDetail";
import { withBoundary } from "../../shared/ErrorBoundary";
import { shortHash } from "../../shared/format";
import { UNNAMED_SAMPLE_LABEL, UNTITLED_MODULE_LABEL } from "../../shared/labels";
import { OptionalLabel } from "../../shared/OptionalLabel";
import { PanelHost } from "../../shared/panel/PanelHost";
import { useListingNeighbors } from "../../workspace/listingOrderStore";
import { PANEL_REGISTRY } from "../../workspace/panelRegistry";
import { ModuleDetailPanel } from "../../workspace/panels/ModuleDetailPanel";
import { SampleDetailPanel } from "../../workspace/panels/SampleDetailPanel";
import type { EntityRef } from "../../workspace/selectionStore";
import { entityRoute } from "../../workspace/useEntityRowInteractions";
import type { PhonePage } from "./phoneView";
import { useBack } from "./useBack";

interface PageHeaderProps {
    readonly title: ReactNode;
    /** The entity the page shows, whose listing the header steps through; `null` for a panel page. */
    readonly entity: EntityRef | null;
}

interface PageProps {
    readonly page: PhonePage;
}

/**
 * A page's header: the way back, the name of what the page shows, and, for an entity that stands
 * in its listing, the steps to the rows before and after it, each replacing the address so the
 * whole walk stays one step from the list.
 */
function PageHeader({ title, entity }: PageHeaderProps): ReactElement {
    const back = useBack();
    const navigate = useNavigate();
    const neighbors = useListingNeighbors(entity);

    function stepTo(hash: string | null): void {
        if (entity === null || hash === null) {
            return;
        }
        void navigate(entityRoute({ kind: entity.kind, hash }), { replace: true });
    }

    return (
        <>
            <button type="button" className="phone-page-back" aria-label="Back" onClick={back}>
                ←
            </button>
            <h1 className="phone-header-title">{title}</h1>
            {entity !== null && neighbors.position !== null && (
                <div className="phone-page-steps">
                    <button
                        type="button"
                        className="phone-page-step"
                        aria-label={`Previous ${entity.kind}`}
                        disabled={neighbors.previous === null}
                        onClick={() => {
                            stepTo(neighbors.previous);
                        }}
                    >
                        ‹
                    </button>
                    <span className="phone-page-position mono">
                        {neighbors.position} / {neighbors.count}
                    </span>
                    <button
                        type="button"
                        className="phone-page-step"
                        aria-label={`Next ${entity.kind}`}
                        disabled={neighbors.next === null}
                        onClick={() => {
                            stepTo(neighbors.next);
                        }}
                    >
                        ›
                    </button>
                </div>
            )}
        </>
    );
}

function SamplePageHeader({ sampleHash }: { readonly sampleHash: string }): ReactElement {
    const state = useSampleDetail(sampleHash);
    const title =
        state.status === "success" ? (
            <OptionalLabel value={state.data.sample.display_name} placeholder={UNNAMED_SAMPLE_LABEL} />
        ) : (
            <span className="mono">{shortHash(sampleHash)}</span>
        );
    return <PageHeader title={title} entity={{ kind: "sample", hash: sampleHash }} />;
}

function ModulePageHeader({ moduleHash }: { readonly moduleHash: string }): ReactElement {
    const state = useModule(moduleHash);
    const title =
        state.status === "success" ? (
            <OptionalLabel value={state.data.title} placeholder={UNTITLED_MODULE_LABEL} />
        ) : (
            <span className="mono">{shortHash(moduleHash)}</span>
        );
    return <PageHeader title={title} entity={{ kind: "module", hash: moduleHash }} />;
}

/** The header of whichever page is open, standing in the shell's own header bar. */
export function PageHeaderFor({ page }: PageProps): ReactElement {
    switch (page.kind) {
        case "sample":
            return <SamplePageHeader sampleHash={page.sampleHash} />;
        case "module":
            return <ModulePageHeader moduleHash={page.moduleHash} />;
        case "panel":
            return <PageHeader title={PANEL_REGISTRY[page.panelId].title} entity={null} />;
    }
}

/**
 * The body of whichever page is open: a sample's transport over its detail, a module's detail, or
 * a panel that has no tab of its own, each in the host the workspace gives the same panel.
 */
export function PageBody({ page }: PageProps): ReactElement {
    switch (page.kind) {
        case "sample":
            return (
                <div className="phone-page-body">
                    {withBoundary(
                        <PanelHost panelId="sample-detail">
                            <SampleDetailPanel />
                        </PanelHost>,
                    )}
                </div>
            );
        case "module":
            return (
                <div className="phone-page-body">
                    {withBoundary(
                        <PanelHost panelId="module-detail">
                            <ModuleDetailPanel />
                        </PanelHost>,
                    )}
                </div>
            );
        case "panel": {
            const Panel = PANEL_REGISTRY[page.panelId].component;
            return (
                <div className="phone-page-body">
                    {withBoundary(
                        <PanelHost panelId={page.panelId}>
                            <Panel />
                        </PanelHost>,
                    )}
                </div>
            );
        }
    }
}
