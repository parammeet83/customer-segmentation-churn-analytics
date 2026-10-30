import { lazy, Suspense } from "react";
import { createBrowserRouter, RouterProvider } from "react-router";
import Layout from "./components/Layout";
import { Loading } from "./components/ui";
import Overview from "./pages/Overview";

const Segmentation = lazy(() => import("./pages/Segmentation"));
const SegmentProfiles = lazy(() => import("./pages/SegmentProfiles"));
const ChurnRisk = lazy(() => import("./pages/ChurnRisk"));
const Explainability = lazy(() => import("./pages/Explainability"));
const Simulator = lazy(() => import("./pages/Simulator"));
const ModelPerformance = lazy(() => import("./pages/ModelPerformance"));
const Methodology = lazy(() => import("./pages/Methodology"));

const page = (el: React.ReactNode) => <Suspense fallback={<Loading label="Loading page" />}>{el}</Suspense>;

const routes = [
  {
    path: "/",
    element: <Layout />,
    children: [
      { index: true, element: <Overview /> },
      { path: "segments", element: page(<Segmentation />) },
      { path: "segment-profiles", element: page(<SegmentProfiles />) },
      { path: "churn-risk", element: page(<ChurnRisk />) },
      { path: "explainability", element: page(<Explainability />) },
      { path: "simulator", element: page(<Simulator />) },
      { path: "model-performance", element: page(<ModelPerformance />) },
      { path: "methodology", element: page(<Methodology />) },
      {
        path: "*",
        element: (
          <div className="panel p-8">
            <h1 className="text-2xl font-bold">Page not found</h1>
          </div>
        ),
      },
    ],
  },
];

const router = createBrowserRouter(routes);

export default function App() {
  return <RouterProvider router={router} />;
}
