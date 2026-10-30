import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import Layout from "../components/Layout";
import ChurnRisk from "../pages/ChurnRisk";
import Explainability from "../pages/Explainability";
import Methodology from "../pages/Methodology";
import ModelPerformance from "../pages/ModelPerformance";
import Overview from "../pages/Overview";
import SegmentProfiles from "../pages/SegmentProfiles";
import Segmentation from "../pages/Segmentation";
import Simulator from "../pages/Simulator";
import { respond } from "./fixtures";

type Handler = (url: string) => { status: number; body: unknown };
let handler: Handler = respond;
const calls: string[] = [];

beforeEach(() => {
  handler = respond;
  calls.length = 0;
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      calls.push(url);
      const { status, body } = handler(url);
      return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
    }),
  );
});
afterEach(() => vi.unstubAllGlobals());

function renderAt(path: string) {
  const router = createMemoryRouter(
    [
      {
        path: "/",
        element: <Layout />,
        children: [
          { index: true, element: <Overview /> },
          { path: "segments", element: <Segmentation /> },
          { path: "segment-profiles", element: <SegmentProfiles /> },
          { path: "churn-risk", element: <ChurnRisk /> },
          { path: "explainability", element: <Explainability /> },
          { path: "simulator", element: <Simulator /> },
          { path: "model-performance", element: <ModelPerformance /> },
          { path: "methodology", element: <Methodology /> },
        ],
      },
    ],
    { initialEntries: [path] },
  );
  render(<RouterProvider router={router} />);
  return router;
}

describe("navigation and states", () => {
  it("shows a loading state, then real API values", async () => {
    renderAt("/");
    expect(screen.getAllByRole("status").length).toBeGreaterThan(0);
    expect(await screen.findByText("Fixture takeaway sentence.")).toBeInTheDocument();
    expect(screen.getByText("0.712")).toBeInTheDocument();
  });

  it("navigates between all eight pages from the sidebar", async () => {
    const router = renderAt("/");
    const nav = screen.getAllByRole("navigation", { name: "Primary" })[0];
    const links = within(nav).getAllByRole("link");
    expect(links.map((l) => l.textContent?.replace(/^[\d·]/, ""))).toEqual([
      "Overview",
      "Customer Segmentation",
      "Segment Profiles",
      "Churn Risk",
      "SHAP Explainability",
      "Retention Simulator",
      "Model Performance",
      "Data & Methodology",
    ]);
    fireEvent.click(links[6]);
    await waitFor(() => expect(router.state.location.pathname).toBe("/model-performance"));
    expect(await screen.findByRole("heading", { name: "Model performance" })).toBeInTheDocument();
  });

  it("shows an error with retry and no placeholder figures when the API fails", async () => {
    handler = (url) => (url.includes("/summary") ? { status: 503, body: { detail: "Database temporarily unavailable" } } : respond(url));
    renderAt("/");
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("Database temporarily unavailable");
    expect(screen.queryByText("0.712")).not.toBeInTheDocument();
    handler = respond;
    fireEvent.click(within(alert).getByRole("button", { name: "Retry" }));
    expect(await screen.findByText("Fixture takeaway sentence.")).toBeInTheDocument();
  });

  it("shows an empty state when filters match nothing", async () => {
    handler = (url) =>
      url.includes("/customers") ? { status: 200, body: { meta: { page: 1, page_size: 25, total: 0, pages: 1 }, items: [] } } : respond(url);
    renderAt("/churn-risk");
    expect(await screen.findByText("No results match the current selection.")).toBeInTheDocument();
  });
});

describe("pages", () => {
  it("segmentation shows segment labels, selected K and silhouette", async () => {
    renderAt("/segments");
    expect(await screen.findByText(/Selected K = 3, silhouette 0.410/)).toBeInTheDocument();
    expect(screen.getAllByText("Fixture Champions").length).toBeGreaterThan(0);
    expect(screen.getByText(/not original RFM/)).toBeInTheDocument();
  });

  it("segment profiles switch segment via tabs", async () => {
    renderAt("/segment-profiles");
    const tab = await screen.findByRole("tab", { name: "Fixture At Risk" });
    fireEvent.click(tab);
    await waitFor(() => expect(calls.some((c) => c.includes("/segments/1"))).toBe(true));
  });

  it("churn risk filters are sent to the API and open the customer drawer", async () => {
    renderAt("/churn-risk");
    expect(await screen.findByText("40 customers")).toBeInTheDocument();
    fireEvent.click(screen.getByLabelText("Top-10% cohort only"));
    expect(await screen.findByText("4 customers")).toBeInTheDocument();
    expect(calls.some((c) => c.includes("top_decile=true"))).toBe(true);
    fireEvent.change(screen.getByLabelText("Risk band"), { target: { value: "Very high" } });
    await waitFor(() => expect(calls.some((c) => c.includes("risk_band=Very+high"))).toBe(true));
    fireEvent.click(screen.getAllByRole("button", { name: /Open details for customer/ })[0]);
    const dialog = await screen.findByRole("dialog");
    expect(await within(dialog).findByRole("list", { name: "Feature contributions" })).toBeInTheDocument();
    expect(within(dialog).getByText(/raises risk/)).toBeInTheDocument();
  });

  it("model performance compares all models and marks the selected one", async () => {
    renderAt("/model-performance");
    expect(await screen.findByText("Model comparison on the held-out test period")).toBeInTheDocument();
    expect(screen.getAllByText("selected").length).toBeGreaterThan(0);
    expect(screen.getAllByText(/HistGradientBoosting/).length).toBeGreaterThan(0);
    expect(screen.getByText("True positive")).toBeInTheDocument();
  });

  it("SHAP page shows global drivers and a customer explanation on demand", async () => {
    renderAt("/explainability");
    expect(await screen.findByText(/Fixture caveat/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "C-000000000000" }));
    expect((await screen.findAllByText(/this raised the predicted inactivity risk/)).length).toBeGreaterThan(0);
  });

  it("retention simulator recalculates immediately and always shows assumptions", async () => {
    renderAt("/simulator");
    expect(await screen.findByText(/Assumptions and method/)).toBeInTheDocument();
    // 4 customers, 10% -> 1 targeted; risk ranking -> p=0.9, rate=1, 90 d, season 0.8 -> at risk 64.8
    expect(screen.getByText(/Targeting 1 customers by risk alone puts an estimated £65/)).toBeInTheDocument();
    const slider = screen.getByLabelText("Customers targeted (% of scored)");
    act(() => {
      fireEvent.change(slider, { target: { value: "50" } });
    });
    expect(screen.getByText(/Targeting 2 customers/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("radio", { name: "Highest risk × value" }));
    expect(screen.getByText(/Targeting 2 customers by risk × value puts an estimated £914/)).toBeInTheDocument();
    expect(screen.getByText(/Fixture disclaimer: scenario estimates only./)).toBeInTheDocument();
  });

  it("methodology shows attribution and the churn definition", async () => {
    renderAt("/methodology");
    expect(await screen.findByText("Chen, D. (2012). Online Retail II.")).toBeInTheDocument();
    expect(await screen.findByText("Fixture churn rule")).toBeInTheDocument();
  });
});
