import SolutionPage from "../../../components/SolutionPage";
import { BookOpen, GraduationCap, Users, Lightbulb } from "lucide-react";

export const metadata = {
  title: "MuseForge for Education — AI Video for Schools & Universities",
  description: "Create educational explainer videos, student project support, and institutional promotional content with MuseForge.",
};

export default function EducationPage() {
  return (
    <SolutionPage
      icon={<BookOpen size={12} />}
      accentColor="#0891b2"
      badge="Educational Institutions"
      heading={<><span style={{ color: "#e2e8f0" }}>AI Video for</span><br /><span className="gradient-text">Classrooms &amp; Campuses</span></>}
      subheading="Give students a professional-grade AI studio for their projects. Create institutional promotional content without a production budget. MuseForge scales from a single teacher to an entire university."
      useCases={[
        {
          icon: <GraduationCap size={20} style={{ color: "#0891b2" }} />,
          title: "Student Film Projects",
          desc: "Students write a story idea; MuseForge generates a complete short film — a powerful introduction to AI-assisted storytelling and production.",
          sample: "Student sci-fi short: 'The Last Signal' — 3 scenes, cinematic preset",
        },
        {
          icon: <BookOpen size={20} style={{ color: "#0891b2" }} />,
          title: "Educational Explainer Videos",
          desc: "Instructors generate visual explainers for complex topics — history re-enactments, scientific concepts, or literature adaptations.",
          sample: "History lesson visualization: Roman Senate chamber — slow cinematic, 16:9",
        },
        {
          icon: <Users size={20} style={{ color: "#0891b2" }} />,
          title: "Campus Promotional Content",
          desc: "Produce campus tour teasers, department showcases, and recruitment videos without booking a film crew.",
          sample: "University open day promo — warm cinematic look, campus characters",
        },
        {
          icon: <Lightbulb size={20} style={{ color: "#0891b2" }} />,
          title: "Creative Media Curriculum",
          desc: "Use MuseForge as a hands-on tool in digital media, film studies, or creative writing classes — students learn AI pipeline fundamentals by doing.",
          sample: "Class exercise: 20 students each generate a different genre short in one session",
        },
      ]}
      differentiators={[
        {
          title: "Demo Mode — Zero Cost for Classroom Exploration",
          desc: "Students can run the full pipeline and see a complete storyboard without spending any credits. Ideal for introductory workshops.",
        },
        {
          title: "Creator Plan for Individual Teachers — $49/mo",
          desc: "25 credits per month is enough for a full semester of student projects — about five 5-scene videos per cohort.",
        },
        {
          title: "Enterprise Licence for Campus-Wide Deployment",
          desc: "Custom credit volume, SSO integration, and a dedicated account manager. Contact us to discuss institution-wide pricing.",
        },
        {
          title: "Safe, Ethical AI Output",
          desc: "MuseForge produces controlled, script-guided visuals from user-written ideas — appropriate for supervised educational use.",
        },
      ]}
      planCard={{
        name: "Creator (Individual Educator)",
        price: "$49",
        period: "/ mo",
        credits: 25,
        highlight: false,
        cta: "Start with Creator",
        ctaHref: "/pricing",
        features: ["25 credits/mo", "Up to 5 scenes", "All presets", "All ratios", "Priority render"],
      }}
      ctaBanner={{
        title: "Need a Campus-Wide Licence?",
        desc: "We offer custom pricing, SSO, and onboarding for universities and school networks. Let's talk.",
        btnText: "Contact Enterprise Sales",
        btnHref: "mailto:enterprise@museforge.ai",
      }}
    />
  );
}
